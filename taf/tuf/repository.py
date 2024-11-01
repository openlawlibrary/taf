"""TUF metadata repository"""


from fnmatch import fnmatch
from functools import reduce
import os
from pathlib import Path
import logging
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional
from securesystemslib.exceptions import StorageError

from securesystemslib.signer import Signer

from tuf.api.metadata import (
    Metadata,
    MetaFile,
    Role,
    Root,
    Snapshot,
    Targets,
    TargetFile,
    Timestamp,
    DelegatedRole,
    Delegations,
)
from tuf.api.serialization.json import JSONSerializer
from taf.exceptions import TAFError
from taf.models.types import RolesIterator, RolesKeysData
from taf.tuf.keys import _get_legacy_keyid
from tuf.repository import Repository


logger = logging.getLogger(__name__)

METADATA_DIRECTORY_NAME = "metadata"
TARGETS_DIRECTORY_NAME = "targets"

MAIN_ROLES = ["root", "targets", "snapshot", "timestamp"]


class MetadataRepository(Repository):
    """TUF metadata repository implementation for on-disk top-level roles.

    Provides methods to read and edit metadata, handling version and expiry
    bumps, and signature creation, and facilitating snapshot and timestamp
    creation.

    Arguments:
        path: Base path of metadata repository.

    Attributes:
        signer_cache: All signers available to the repository. Keys are role
            names, values are lists of signers. On `close` each signer for a
            role is used to sign the related role metadata.
    """

    expiration_intervals = {"root": 365, "targets": 90, "snapshot": 7, "timestamp": 1}

    serializer = JSONSerializer(compact=False)

    def __init__(self, path: Path) -> None:
        self.signer_cache: Dict[str, Dict[str, Signer]] = {}
        self._path = path

        self._snapshot_info = MetaFile(1)
        self._targets_infos: Dict[str, MetaFile] = defaultdict(lambda: MetaFile(1))

    @property
    def metadata_path(self) -> Path:
        return self._path / METADATA_DIRECTORY_NAME

    @property
    def targets_path(self):
        return self._path / TARGETS_DIRECTORY_NAME

    @property
    def targets_infos(self) -> Dict[str, MetaFile]:
        # tracks targets and root metadata changes, needed in `do_snapshot`
        return self._targets_infos

    @property
    def snapshot_info(self) -> MetaFile:
        # tracks snapshot metadata changes, needed in `do_timestamp`
        return self._snapshot_info


    def all_target_files(self):
        """
        Return a set of relative paths of all files inside the targets
        directory
        """
        targets = []
        # Assume self.targets_path is a Path object, or convert it if necessary
        base_path = Path(self.targets_path)

        for filepath in base_path.rglob('*'):
            if filepath.is_file():
                # Get the relative path to the base directory and convert it to a POSIX path
                relative_path = filepath.relative_to(base_path).as_posix()
                targets.append(relative_path)

        return set(targets)

    def add_target_files(self, target_files: List[TargetFile]) -> None:
        """Add target files to top-level targets metadata."""
        with self.edit_targets() as targets:
            for target_file in target_files:
                targets.targets[target_file.path] = target_file


    def add_keys(self, signers: List[Signer], role: str) -> None:
        """Add signer public keys for role to root and update signer cache."""
        with self.edit_root() as root:
            for signer in signers:
                key = signer.public_key
                self.signer_cache[role][key.keyid] = signer
                root.add_key(key, role)

        # Make sure the targets role gets signed with its new key, even though
        # it wasn't updated itself.
        if role == "targets":
            with self.edit_targets():
                pass

        self.do_snapshot()
        self.do_timestamp()

    def open(self, role: str) -> Metadata:
        """Read role metadata from disk."""
        try:
            return Metadata.from_file(self.metadata_path / f"{role}.json")
        except StorageError:
            raise TAFError(f"Metadata file {self.metadata_path} does not exist")

    def check_if_role_exists(self, role_name):
        role = self._role_obj(role_name)
        return role is not None

    def check_roles_expiration_dates(
        self, interval=None, start_date=None, excluded_roles=None
    ):
        """Determines which metadata roles have expired, or will expire within a time frame.
        Args:
        - interval(int): Number of days to look ahead for expiration.
        - start_date(datetime): Start date to look for expiration.
        - excluded_roles(list): List of roles to exclude from the search.

        Returns:
        - A dictionary of roles that have expired, or will expire within the given time frame.
        Results are sorted by expiration date.
        """
        if start_date is None:
            start_date = datetime.now(timezone.utc)
        if interval is None:
            interval = 30
        expiration_threshold = start_date + timedelta(days=interval)

        if excluded_roles is None:
            excluded_roles = []

        target_roles = self.get_all_targets_roles()
        main_roles = ["root", "targets", "snapshot", "timestamp"]
        existing_roles = list(set(target_roles + main_roles) - set(excluded_roles))

        expired_dict = {}
        will_expire_dict = {}
        for role in existing_roles:
            expiry_date = self.get_expiration_date(role)
            if start_date > expiry_date:
                expired_dict[role] = expiry_date
            elif expiration_threshold >= expiry_date:
                will_expire_dict[role] = expiry_date
        # sort by expiry date
        expired_dict = {
            k: v for k, v in sorted(expired_dict.items(), key=lambda item: item[1])
        }
        will_expire_dict = {
            k: v for k, v in sorted(will_expire_dict.items(), key=lambda item: item[1])
        }

        return expired_dict, will_expire_dict


    def close(self, role: str, md: Metadata) -> None:
        """Bump version and expiry, re-sign, and write role metadata to disk."""

        # expiration date is updated before close is called
        md.signed.version += 1

        md.signatures.clear()
        for signer in self.signer_cache[role].values():
            md.sign(signer, append=True)

        fname = f"{role}.json"

        # Track snapshot, targets and root metadata changes, needed in
        # `do_snapshot` and `do_timestamp`
        if role == "snapshot":
            self._snapshot_info.version = md.signed.version
        elif role != "timestamp":  # role in [root, targets, <delegated targets>]
            self._targets_infos[fname].version = md.signed.version

        # Write role metadata to disk (root gets a version-prefixed copy)
        md.to_file(self.metadata_path / fname, serializer=self.serializer)

        if role == "root":
            md.to_file(self.metadata_path / f"{md.signed.version}.{fname}")


    def create(self, roles_keys_data: RolesKeysData, signers: dict):
        """Create a new metadata repository on disk.

        1. Create metadata subdir (fail, if exists)
        2. Create initial versions of top-level metadata
        3. Perform top-level delegation using keys from passed signers.

        Args:
            signers: A dictionary, where dict-keys are role names and values
                are dictionaries, where-dict keys are keyids and values
                are signers.
        """
        self.metadata_path.mkdir()
        self.signer_cache  = defaultdict(dict)

        root = Root(consistent_snapshot=False)

        # Snapshot tracks targets and root versions. targets v1 is included by
        # default in snapshot v1. root must be added explicitly.
        sn = Snapshot()
        sn.meta["root.json"] = MetaFile(1)

        for role in RolesIterator(roles_keys_data.roles, include_delegations=False):
            if not role.is_yubikey:
                if signers is None:
                    raise TAFError(f"Cannot setup role {role.name}. Keys not specified")
                for signer in signers[role.name]:
                    key_id = _get_legacy_keyid(signer.public_key)
                    self.signer_cache[role.name][key_id] = signer
                    root.add_key(signer.public_key, role.name)
            root.roles[role.name].threshold = role.threshold

        targets = Targets()
        target_roles = {"targets": targets}
        delegations_per_parent = defaultdict(dict)
        for role in RolesIterator(roles_keys_data.roles.targets):
            if role.parent is None:
                continue
            parent = role.parent.name
            parent_obj = target_roles.get(parent)
            keyids = []
            for signer in signers[role.name]:
                key_id = _get_legacy_keyid(signer.public_key)
                self.signer_cache[role.name][key_id] = signer
                keyids.append(key_id)
            delegated_role = DelegatedRole(
                name=role.name,
                threshold=role.threshold,
                paths=role.paths,
                terminating=role.terminating,
                keyids=keyids,
            )
            delegated_metadata = Targets()
            target_roles[role.name] = delegated_metadata
            delegations_per_parent[parent][role.name] = delegated_role
            sn.meta[f"{role.name}.json"] = MetaFile(1)

        for parent, role_data in delegations_per_parent.items():
            parent_obj = target_roles[parent]
            keys = {}
            for role_name in role_data:
                for key_id, signer in  self.signer_cache[role_name].items():
                    keys[key_id] = signer.public_key

            delegations = Delegations(roles=role_data, keys=keys)
            parent_obj.delegations = delegations

        for signed in [root, Timestamp(), sn, targets]:
            # Setting the version to 0 here is a trick, so that `close` can
            # always bump by the version 1, even for the first time
            self._set_default_expiration_date(signed)
            signed.version = 0  # `close` will bump to initial valid verison 1
            self.close(signed.type, Metadata(signed))

        for name, signed in target_roles.items():
            if name != "targets":
                self._set_default_expiration_date(signed)
                signed.version = 0  # `close` will bump to initial valid verison 1
                self.close(name, Metadata(signed))


    def add_delegation(self, role_data):
        pass

    def find_delegated_roles_parent(self, delegated_role, parent=None):
        if parent is None:
            parent = "targets"

        parents = [parent]

        while parents:
            parent = parents.pop()
            parent_obj = self._signed_obj(parent)
            if parent_obj.delegations:
                for delegation in parent_obj.delegations.roles:
                    if delegation == delegated_role:
                        return parent
                    parents.append(delegation)
        return None


    def get_keyids_of_role(self, role_name):
        role_obj = self._role_obj(role_name)
        return role_obj.keyids

    def get_delegations_of_role(self, role_name):
        signed_obj = self._signed_obj(role_name)
        return signed_obj.delegations.roles

    def find_keys_roles(self, public_keys, check_threshold=True):
        """Find all roles that can be signed by the provided keys.
        A role can be signed by the list of keys if at least the number
        of keys that can sign that file is equal to or greater than the role's
        threshold
        """
        roles = []
        for role in MAIN_ROLES:
            roles.append((role, None))
        keys_roles = []
        key_ids = [_get_legacy_keyid(public_key) for public_key in public_keys]
        while roles:
            role_name, parent = roles.pop()
            role_obj = self._role_obj(role_name, parent)
            signed_obj = self._signed_obj(role_name)
            target_roles_key_ids = role_obj.keyids
            threshold = role_obj.threshold
            num_of_signing_keys = len(
                set(target_roles_key_ids).intersection(key_ids)
            )
            if (
                (not check_threshold and num_of_signing_keys >= 1)
                or num_of_signing_keys >= threshold
            ):
                keys_roles.append(role_name)

            if role_name not in MAIN_ROLES or role_name == "targets":
                if signed_obj.delegations:
                    for delegation in signed_obj.delegations.roles:
                        roles.append((delegation, role_name))

        return keys_roles

    def find_associated_roles_of_key(self, public_key):
        """
        Find all roles whose metadata files can be signed by this key
        Threshold is not important, as long as the key is one of the signing keys
        """
        return self.find_keys_roles([public_key], check_threshold=False)

    def get_all_roles(self):
        """
        Return a list of all defined roles, main roles combined with delegated targets roles
        """
        all_target_roles = self.get_all_targets_roles()
        all_roles = ["root", "snapshot", "timestamp"] + all_target_roles
        return all_roles

    def get_all_targets_roles(self):
        """
        Return a list containing names of all target roles
        """
        target_roles = ["targets"]
        all_roles = []

        while target_roles:
            role = target_roles.pop()
            all_roles.append(role)
            role_metadata = self._signed_obj(role)
            if role_metadata.delegations:
                for delegation in role_metadata.delegations.roles:
                    target_roles.append(delegation)

        return all_roles

    def get_expiration_date(self, role: str) -> datetime:
        meta_file = self._signed_obj(role)
        if meta_file is None:
            raise TAFError(f"Role {role} does not exist")
        return meta_file.expires

    def get_role_threshold(self, role: str, parent: Optional[str]=None ) -> int:
        """Get threshold of the given role

        Args:
        - role(str): TUF role (root, targets, timestamp, snapshot or delegated one)
        - parent_role(str): Name of the parent role of the delegated role. If not specified,
                            it will be set automatically, but this might be slow if there
                            are many delegations.

        Returns:
        Role's signatures threshold

        Raises:
        - TAFError if the role does not exist or if metadata files are invalid
        """
        role_obj = self._role_obj(role, parent)
        if role_obj is None:
            raise TAFError(f"Role {role} does not exist")
        return role_obj.threshold

    def get_role_paths(self, role, parent_role=None):
        """Get paths of the given role

        Args:
        - role(str): TUF role (root, targets, timestamp, snapshot or delegated one)
        - parent_role(str): Name of the parent role of the delegated role. If not specified,
                            it will be set automatically, but this might be slow if there
                            are many delegations.

        Returns:
        Defined delegated paths of delegate target role or * in case of targets

        Raises:
        - securesystemslib.exceptions.FormatError: If the arguments are improperly formatted.
        - securesystemslib.exceptions.UnknownRoleError: If 'rolename' has not been delegated by this
        """
        if role == "targets":
            return "*"
        role = self._role_obj(role)
        if role is None:
            raise TAFError(f"Role {role} does not exist")
        return role.paths

    def get_role_from_target_paths(self, target_paths):
        """
        Find a common role that can be used to sign given target paths.

        NOTE: Currently each target has only one mapped role.
        """
        targets_roles = self.map_signing_roles(target_paths)
        roles = list(targets_roles.values())

        try:
            # all target files should have at least one common role
            common_role = reduce(
                set.intersection,
                [set([r]) if isinstance(r, str) else set(r) for r in roles],
            )
        except TypeError:
            return None

        if not common_role:
            return None

        return common_role.pop()


    # TODO
    def get_signed_target_files(self):
        """Return all target files signed by all roles.

        Args:
        - None

        Returns:
        - Set of all target paths relative to targets directory
        """
        all_roles = self.get_all_targets_roles()
        return self.get_singed_target_files_of_roles(all_roles)

    # TODO
    def get_singed_target_files_of_roles(self, roles):
        """Return all target files signed by the specified roles

        Args:
        - roles whose target files will be returned

        Returns:
        - Set of paths of target files of a role relative to targets directory
        """
        if roles is None:
            roles = self.get_all_targets_roles()
        role_obj = self._role_obj("targets")
        import pdb; pdb.set_trace()
        # return set(
        #     reduce(
        #         operator.iconcat,
        #         [self._role_obj(role).target_files for role in roles],
        #         [],
        #     )
        # )

    # TODO
    def get_signed_targets_with_custom_data(self, roles):
        """Return all target files signed by the specified roles and and their custom data
        as specified in the metadata files

        Args:
        - roles whose target files will be returned

        Returns:
        - A dictionary whose keys are parts of target files relative to the targets directory
        and values are custom data dictionaries.
        """
        if roles is None:
            roles = self.get_all_targets_roles()
        target_files = {}
        for role in roles:
            roles_targets = self._role_obj(role).target_files
            for target_file, custom_data in roles_targets.items():
                target_files.setdefault(target_file, {}).update(custom_data)
        return target_files

    def map_signing_roles(self, target_filenames):
        """
        For each target file, find delegated role responsible for that target file based
        on the delegated paths. The most specific role (meaning most deeply nested) whose
        delegation path matches the target's path is returned as that file's matching role.
        If there are no delegated roles with a path that matches the target file's path,
        'targets' role will be returned as that file's matching role. Delegation path
        is expected to be relative to the targets directory. It can be defined as a glob
        pattern.
        """

        roles = ["targets"]
        roles_targets = {
            target_filename: "targets" for target_filename in target_filenames
        }
        while roles:
            role = roles.pop()
            path_patterns = self.get_role_paths(role)
            for path_pattern in path_patterns:
                for target_filename in target_filenames:
                    if fnmatch(
                        target_filename.lstrip(os.sep),
                        path_pattern.lstrip(os.sep),
                    ):
                        roles_targets[target_filename] = role

            role_obj = self._signed_obj(role)
            if role_obj.delegations:
                for delegation in role_obj.delegations.roles:
                    roles.append(delegation)

        return roles_targets


    def _signed_obj(self, role):
        md = self.open(role)
        try:
            signed_data = md.to_dict()["signed"]
            role_to_role_class = {
                "root": Root,
                "targets": Targets,
                "snapshot": Snapshot,
                "timestamp": Timestamp
            }
            role_class =  role_to_role_class.get(role, Targets)
            return role_class.from_dict(signed_data)
        except (KeyError, ValueError):
            raise TAFError(f"Invalid metadata file {role}.json")

    def _set_default_expiration_date(self, signed):
        interval = self.expiration_intervals[signed.type]
        start_date = datetime.now(timezone.utc)
        expiration_date = start_date + timedelta(interval)
        signed.expires = expiration_date

    def set_metadata_expiration_date(self, role, start_date=None, interval=None):
        """Set expiration date of the provided role.

        Args:
        - role(str): TUF role (root, targets, timestamp, snapshot or delegated one)
        - start_date(datetime): Date to which the specified interval is added when calculating
                                expiration date. If a value is not provided, it is set to the
                                current time.
        - interval(int): A number of days added to the start date.
                        If not provided, the default value is set based on the role:

                            root - 365 days
                            targets - 90 days
                            snapshot - 7 days
                            timestamp - 1 day
                            all other roles (delegations) - same as targets

        Returns:
        None

        Raises:
        - securesystemslib.exceptions.FormatError: If the arguments are improperly formatted.
        - securesystemslib.exceptions.UnknownRoleError: If 'rolename' has not been delegated by
                                                        this targets object.
        """
        md = self.open(role)
        start_date = datetime.now(datetime.timezone.utc)
        if interval is None:
            try:
                interval = self.expiration_intervals[role]
            except KeyError:
                interval = self.expiration_intervals["targets"]
        expiration_date = start_date + timedelta(interval)
        md.signed.expires = expiration_date

        self.close(role, md)

    def _role_obj(self, role, parent=None):
        if role in MAIN_ROLES:
            md = self.open("root")
            try:
                data = md.to_dict()["signed"]["roles"][role]
                return Role.from_dict(data)
            except (KeyError, ValueError):
                raise TAFError("root.json is invalid")
        else:
            parent_name = self.find_delegated_roles_parent(role, parent)
            if parent_name is None:
                return None
            md = self.open(parent_name)
            delegations_data = md.to_dict()["signed"]["delegations"]["roles"]
            for delegation in delegations_data:
                if delegation["name"] == role:
                    try:
                        return DelegatedRole.from_dict(delegation)
                    except (KeyError, ValueError):
                        raise TAFError(f"{delegation}.json is invalid")
            return None
