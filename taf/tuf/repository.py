"""TUF metadata repository"""


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
)
from taf.exceptions import TAFError
from tuf.repository import Repository

logger = logging.getLogger(__name__)

METADATA_DIRECTORY_NAME = "metadata"

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

    def __init__(self, path: Path) -> None:
        self.signer_cache: Dict[str, Dict[str, Signer]] = {}
        self._path = path

        self._snapshot_info = MetaFile(1)
        self._targets_infos: Dict[str, MetaFile] = defaultdict(lambda: MetaFile(1))

    @property
    def metadata_path(self) -> Path:
        return self._path / METADATA_DIRECTORY_NAME

    @property
    def targets_infos(self) -> Dict[str, MetaFile]:
        # tracks targets and root metadata changes, needed in `do_snapshot`
        return self._targets_infos

    @property
    def snapshot_info(self) -> MetaFile:
        # tracks snapshot metadata changes, needed in `do_timestamp`
        return self._snapshot_info

    def add_target_files(self, target_files: List[TargetFile]) -> None:
        """Add target files to top-level targets metadata."""
        with self.edit_targets() as targets:
            for target_file in target_files:
                targets.targets[target_file.path] = target_file

        self.do_snapshot()
        self.do_timestamp()

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
        md.to_file(self.metadata_path / fname)
        if role == "root":
            md.to_file(self.metadata_path / f"{md.signed.version}.{fname}")

    def create(self, signers: Dict[str, Dict[str, Signer]]):
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
        self.signer_cache = signers

        root = Root(consistent_snapshot=False)
        for role in ["root", "timestamp", "snapshot", "targets"]:
            for signer in self.signer_cache[role].values():
                root.add_key(signer.public_key, role)

        # Snapshot tracks targets and root versions. targets v1 is included by
        # default in snapshot v1. root must be added explicitly.
        sn = Snapshot()
        sn.meta["root.json"] = MetaFile(1)

        for signed in [root, Timestamp(), sn, Targets()]:
            # Setting the version to 0 here is a trick, so that `close` can
            # always bump by the version 1, even for the first time
            signed.version = 0  # `close` will bump to initial valid verison 1
            self.close(signed.type, Metadata(signed))

    def find_delegated_roles_parent(self, delegated_role, parent=None):
        if parent is None:
            parent = "targets"

        parents = [parent]

        while parents:
            parent = parents.pop()
            parent_obj = self._signed_obj(parent)
            for delegation in parent_obj.delegations.roles:
                if delegation == delegated_role:
                    return parent
                parents.append(delegation)
        return None


    def _signed_obj(self, role):
        md = self.open(role)
        try:
            singed_data = md.to_dict()["signed"]
            role_to_role_class = {
                "root": Root,
                "targets": Targets,
                "snapshot": Snapshot,
                "timestamp": Timestamp
            }
            role_class =  role_to_role_class.get(role, Targets)
            return role_class.from_dict(singed_data)
        except (KeyError, ValueError):
            raise TAFError(f"Invalid metadata file {role}.json")

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
                        return Role.from_dict(delegation)
                    except (KeyError, ValueError):
                        raise TAFError(f"{delegation}.json is invalid")
            return None

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
        start_date = datetime.datetime.now()
        if interval is None:
            try:
                interval = self.expiration_intervals[role]
            except KeyError:
                interval = self.expiration_intervals["targets"]
        expiration_date = start_date + datetime.timedelta(interval)
        md.signed.expires = expiration_date

        self.close(role, md)
