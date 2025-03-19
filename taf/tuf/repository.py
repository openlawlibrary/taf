"""TUF metadata repository"""


from fnmatch import fnmatch
from functools import reduce
import json
import operator
import os
from pathlib import Path
import logging
from collections import defaultdict
from datetime import datetime, timedelta, timezone
import shutil
from typing import Any, Dict, List, Optional, Set, Tuple, Union
from securesystemslib.exceptions import StorageError
from cryptography.hazmat.primitives import serialization

from securesystemslib.signer import Signer
from securesystemslib import hash as sslib_hash

from taf import YubikeyMissingLibrary

from securesystemslib.storage import FilesystemBackend

from taf.yubikey.yubikey_manager import YubiKeyStore
from tuf.api.metadata import Signed

try:
    import taf.yubikey.yubikey as yk
except ImportError:
    yk = YubikeyMissingLibrary()  # type: ignore

from taf.constants import DEFAULT_RSA_SIGNATURE_SCHEME
from taf.utils import (
    default_backend,
    get_file_details,
    on_rm_error,
    normalize_file_line_endings,
)
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
from taf.exceptions import InvalidKeyError, SignersNotLoaded, TAFError, TargetsError
from taf.models.types import RolesIterator, RolesKeysData, TargetsRole
from taf.tuf.keys import SSlibKey, _get_legacy_keyid, get_sslib_key_from_value
from tuf.repository import Repository

from securesystemslib.signer import CryptoSigner


logger = logging.getLogger(__name__)

# TODO remove this, use from constants or remove from constants
METADATA_DIRECTORY_NAME = "metadata"
TARGETS_DIRECTORY_NAME = "targets"

MAIN_ROLES = ["root", "targets", "snapshot", "timestamp"]

DISABLE_KEYS_CACHING = False
HASH_FUNCTION = "sha256"
HASH_ALGS = ["sha256", "sha512"]


class FakeDelegatedRole:
    """A fake role to bypass validation checks in Delegations."""

    def to_dict(self) -> Dict[str, Any]:
        return {}


class EmptyDelegations(Delegations):
    """Extended version of Delegations that allows empty roles by inserting and removing fake data.
    Needed for backwards compatibility with old TAF.
    Implements a to_dict that returns this:
    "delegations": {
        "keys": {},
        "roles": []
    }
    """

    def __init__(self):
        """Initialize with fake data to bypass the validation in Delegations."""
        super().__init__(
            keys={}, roles={"placeholder": FakeDelegatedRole()}
        )  # Insert fake role

    def to_dict(self) -> Dict[str, Any]:
        """Return the dict representation of self, ensuring 'roles' is always an empty list."""
        res_dict = super().to_dict()

        # Remove the placeholder role
        if "roles" in res_dict:
            res_dict["roles"] = []

        return res_dict


def get_role_metadata_path(role: str) -> str:
    """
    Arguments:
        role: Name of a TUF role, main or delegated

    Return:
        Path of the metadata file corresponding to the specified role,
        relative to the repository's root
    """
    return f"{METADATA_DIRECTORY_NAME}/{role}.json"


def get_target_path(target_name: str) -> str:
    """
    Arguments:
        target_name: Name of the target file expected to be inside the targets directory

    Return:
        Path of the specified target file relative to the repository's root
    """
    return f"{TARGETS_DIRECTORY_NAME}/{target_name}"


def is_delegated_role(role: str) -> bool:
    return role not in ("root", "targets", "snapshot", "timestamp")


def is_auth_repo(repo_path: Union[Path, str]) -> bool:
    """Check if the given path contains a valid TUF repository"""
    try:
        MetadataRepository(path=repo_path).open(Root.type)
        return True
    except Exception:
        return False


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
        metadata_to_keep_open: A set containing metadata whose version numbers should not
        be increased when saving to disk. This makes it possible to combine multiple updates
    """

    expiration_intervals = {"root": 365, "targets": 90, "snapshot": 7, "timestamp": 1}

    serializer = JSONSerializer(compact=False)

    def __init__(self, path: Union[Path, str], *args, **kwargs) -> None:
        storage_backend = kwargs.pop("storage", None)
        pin_manager = kwargs.pop("pin_manager", None)
        super().__init__(*args, **kwargs)
        self.signer_cache: Dict[str, Dict[str, Signer]] = defaultdict(dict)
        self.path = Path(path)

        self._snapshot_info = MetaFile(1)
        self._targets_infos: Dict[str, MetaFile] = defaultdict(lambda: MetaFile(1))
        if storage_backend:
            self.storage_backend = storage_backend
        else:
            self.storage_backend = FilesystemBackend()
        self._metadata_to_keep_open: Set[str] = set()
        self.pin_manager = pin_manager
        self.yubikey_store = YubiKeyStore()
        self._keys_name_mappings: Optional[Dict[str, str]] = None

    @property
    def keys_name_mappings(self):
        """
        Key id to key name
        """
        try:
            if self._keys_name_mappings is None:
                self._keys_name_mappings = self.load_key_names()
        except TAFError:
            # repository does not exist yet, so no metadata files
            self._keys_name_mappings = {}
        return self._keys_name_mappings

    @property
    def keys_name_mappings_reverse(self):
        """
        Key name to key id
        """
        if not self.keys_name_mappings:
            return None
        return {value: key for key, value in self.keys_name_mappings.items()}

    @property
    def metadata_path(self) -> Path:
        """
        Full path of the metadata directory.
        """
        return self.path / METADATA_DIRECTORY_NAME

    @property
    def targets_path(self):
        """
        Full path of the targets directory.
        """
        return self.path / TARGETS_DIRECTORY_NAME

    @property
    def targets_infos(self) -> Dict[str, MetaFile]:
        """
        Tracks targets and root metadata changes, needed in `do_snapshot`
        """
        return self._targets_infos

    @property
    def snapshot_info(self) -> MetaFile:
        """
        Tracks snapshot metadata changes, needed in `do_timestamp`
        """
        return self._snapshot_info

    def add_key_names(self, keys_keys_name_mappings: Dict) -> None:
        for key_id, key_name in keys_keys_name_mappings.items():
            self.add_key_name(key_name, key_id, overwrite=True)

    def add_key_name(self, key_name, key_id, overwrite=False):
        # make sure _keys_name_mappings is initialized
        self.keys_name_mappings
        if overwrite or not key_id in self.keys_name_mappings:
            self._keys_name_mappings[key_id] = key_name

    def add_default_names_of_role(self, role_name):
        key_names = self.get_key_names_of_role(role_name)
        key_ids = self.get_keyids_of_role(role_name)
        for key_name, key_id in zip(key_names, key_ids):
            self.add_key_name(key_name, key_id)

    def all_target_files(self) -> Set:
        """
        Return a set of relative paths of all files inside the targets
        directory
        """
        targets = []
        # Assume self.targets_path is a Path object, or convert it if necessary
        base_path = Path(self.targets_path)

        for filepath in base_path.rglob("*"):
            if filepath.is_file():
                # Get the relative path to the base directory and convert it to a POSIX path
                relative_path = filepath.relative_to(base_path).as_posix()
                targets.append(relative_path)

        return set(targets)

    def add_metadata_keys(self, roles_keys: Dict[str, List]) -> Tuple[Dict, Dict, Dict]:
        """Add signer public keys for role to root and update signer cache without updating snapshot and timestamp.

        Return:
            added_keys, already_added_keys, invalid_keys
        """
        already_added_keys = defaultdict(list)
        invalid_keys = defaultdict(list)
        added_keys = defaultdict(list)

        def _filter_if_can_be_added(roles):
            keys_to_be_added = defaultdict(list)
            for role, keys in roles_keys.items():
                if role in roles:
                    for key in keys:
                        try:
                            if self.is_valid_metadata_key(role, key):
                                already_added_keys[role].append(key)
                                continue
                        except TAFError:
                            invalid_keys[role].append(key)
                            continue
                        keys_to_be_added[role].append(key)
            return keys_to_be_added

        parents = self.find_parents_of_roles(list(roles_keys.keys()))
        self.verify_signers_loaded(parents)

        # when a key is added to one of the main roles
        # root is modified
        keys_to_be_added_to_root = _filter_if_can_be_added(MAIN_ROLES)
        if keys_to_be_added_to_root:
            with self.edit_root() as root:
                for role, keys in keys_to_be_added_to_root.items():
                    for key in keys:
                        root.add_key(key, role)
                        added_keys[role].append(key)

        other_roles = [role for role in roles_keys if role not in MAIN_ROLES]
        keys_to_be_added_to_targets = _filter_if_can_be_added(other_roles)

        roles_by_parents = defaultdict(list)
        if keys_to_be_added_to_targets:
            # group other roles by parents
            for role, keys in keys_to_be_added_to_targets.items():
                parent = self.find_delegated_roles_parent(role)
                roles_by_parents[parent].append(role)

            for parent, roles in roles_by_parents.items():
                with self.edit(parent) as parent_role:
                    for role in roles:
                        keys = roles_keys[role]
                        for key in keys:
                            parent_role.add_key(key, role)
                            added_keys[role].append(key)

        return added_keys, already_added_keys, invalid_keys

    def add_signers_to_cache(self, roles_signers: Dict):
        for role, signers in roles_signers.items():
            if self._role_obj(role):
                self._load_role_signers(role, signers)

    def add_target_files_to_role(self, added_data: Dict[str, Dict]) -> None:
        """Add target files to top-level targets metadata.

        Arguments:
            added_data(dict): Dictionary of new data whose keys are target paths of repositories
            (as specified in targets.json, relative to the targets dictionary).
            The values are of form:
                {
                    target: content of the target file
                    custom: {
                        custom_field1: custom_value1,
                        custom_field2: custom_value2
                    }
                }
        """
        self.modify_targets(added_data=added_data)

    def add_path_to_delegated_role(self, role: str, paths: List[str]) -> bool:
        """
        Add delegated paths to delegated role and return True if successful

        Arguments:
            role: Name of a delegated target role
            path: A list of paths to be appended to a list of the role's delegated pats
        """
        if not self.check_if_role_exists(role):
            raise TAFError(f"Role {role} does not exist")

        parent_role = self.find_delegated_roles_parent(role)
        if parent_role is None:
            return False
        if all(
            path in self.get_delegations_of_role(parent_role)[role].paths
            for path in paths
        ):
            return False
        if parent_role:
            self.verify_signers_loaded([parent_role])
            with self.edit(parent_role) as parent:
                parent.delegations.roles[role].paths.extend(paths)
            return True
        return False

    def add_new_roles_to_snapshot(self, roles: List[str]) -> None:
        """
        Add versions of newly created target roles to the snapshot.
        Also update the versions of their parent roles, which are modified
        when a new delegated role is added.
        """
        with self.edit(Snapshot.type) as sn:
            parents_of_roles = set()
            for role in roles:
                sn.meta[f"{role}.json"] = MetaFile(1)
                parent_role = self.find_delegated_roles_parent(role)
                parents_of_roles.add(parent_role)
            for parent_role in parents_of_roles:
                sn.meta[f"{parent_role}.json"].version = (
                    sn.meta[f"{parent_role}.json"].version + 1
                )

    def add_to_open_metadata(self, roles: List[str]) -> None:
        """
        In order to execute several methods before updating the metadata on disk,
        some metadata might need to be kept open, which is done by adding them to
        _metadata_to_keep_open list.
        This method adds all roles from the provided list to _metadata_to_keep_open.
        """
        self._metadata_to_keep_open.update(roles)

    def open(self, role: str) -> Metadata:
        """Read role metadata from disk."""
        try:
            path = self.metadata_path / f"{role}.json"
            return Metadata.from_file(path, storage_backend=self.storage_backend)
        except StorageError:
            raise TAFError(f"Metadata file {path} does not exist")

    def calculate_hashes(self, md: Metadata, algorithms: List[str]) -> Dict:
        """
        Calculate hashes of the specified signed metadata after serializing
        it using the previously initialized serializer.
        Hashes are computed for each specified algorithm.

        Arguments:
            md: Signed metadata
            algorithms: A list of hash algorithms (e.g., 'sha256', 'sha512').
        Return:
            A dcitionary mapping algorithms and calculated hashes
        """
        hashes = {}
        data = md.to_bytes(serializer=self.serializer)
        for algo in algorithms:
            digest_object = sslib_hash.digest(algo)
            digest_object.update(data)

            hashes[algo] = digest_object.hexdigest()
        return hashes

    def calculate_length(self, md: Metadata) -> int:
        """
        Calculate length of the specified signed metadata after serializing
        it using the previously initialized serializer.

        Arguments:
            md: Signed metadata
        Return:
            Langth of the signed metadata
        """
        data = md.to_bytes(serializer=self.serializer)
        return len(data)

    def check_if_keys_loaded(self, role_name: str) -> bool:
        """
        Check if at least a threshold of signers of the specified role
        has been added to the signer cache.
        """
        threshold = self.get_role_threshold(role_name)
        return (
            role_name in self.signer_cache
            and len(self.signer_cache[role_name]) >= threshold
        )

    def check_if_role_exists(self, role_name: str) -> bool:
        """
        Given a name of a main or delegated target role, return True if it exist
        """
        role = self._role_obj(role_name)
        return role is not None

    def check_roles_expiration_dates(
        self,
        interval: Optional[int] = None,
        start_date: Optional[datetime] = None,
        excluded_roles: Optional[List[str]] = None,
    ) -> Tuple[Dict, Dict]:
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

    def _create_target_file(self, target_path: Path, target_data: Dict) -> None:
        """
        Writes the specified data to a target file and stores it on disk.
        Target data is of the following form:
        {
            target: content of the target file, string or Dict (json)
            custom: {
                custom_field1: custom_value1,
                custom_field2: custom_value2
            }
        }
        """
        # if the target's parent directory should not be "targets", create
        # its parent directories if they do not exist
        target_dir = target_path.parent
        target_dir.mkdir(parents=True, exist_ok=True)

        # create the target file
        content = target_data.get("target", None)
        if content is None:
            if not target_path.is_file():
                target_path.touch()
        else:
            with open(str(target_path), "w") as f:
                if isinstance(content, dict):
                    json.dump(content, f, indent=4)
                else:
                    f.write(content)

    def clear_open_metadata(self) -> None:
        """
        Removes everything from the _metadata_to_keep_open list
        """
        self._metadata_to_keep_open = set()

    def close(self, role: str, md: Metadata) -> None:
        """Bump version and expiry, re-sign, and write role metadata to disk."""

        # expiration date is updated before close is called
        if role not in self._metadata_to_keep_open:
            md.signed.version += 1

        md.signatures.clear()
        for signer in self.signer_cache[role].values():
            md.sign(signer, append=True)

        fname = f"{role}.json"

        # Track snapshot, targets and root metadata changes, needed in
        # `do_snapshot` and `do_timestamp`
        if role == "snapshot":
            self._snapshot_info.version = md.signed.version
            self._snapshot_info.hashes = self.calculate_hashes(md, HASH_ALGS)
            self._snapshot_info.length = self.calculate_length(md)
            root_version = self.signed_obj("root").version
            md.signed.meta["root.json"].version = root_version

        elif role != "timestamp":  # role in [root, targets, <delegated targets>]
            self._targets_infos[fname].version = md.signed.version

        # Write role metadata to disk (root gets a version-prefixed copy)
        md.to_file(
            self.metadata_path / fname,
            serializer=self.serializer,
            storage_backend=self.storage_backend,
        )

        if role == "root":
            md.to_file(
                self.metadata_path / f"{md.signed.version}.{fname}",
                serializer=self.serializer,
            )

    def create(
        self,
        roles_keys_data: RolesKeysData,
        signers: dict,
        additional_verification_keys: Optional[dict] = None,
    ) -> None:
        """Create a new metadata repository on disk.

        1. Create metadata subdir (fail, if exists)
        2. Create initial versions of top-level metadata
        3. Perform top-level delegation using keys from passed signers.

        Arguments:
            roles_keys_data: an object containing information about roles, their threshold, delegations etc.
            signers: A dictionary, where dict-keys are role names and values
                are dictionaries, where-dict keys are keyids and values
                are signers.
            additional_verification_keys: A dictionary where keys are names of roles and values are lists
                of public keys that should be registered as the corresponding role's keys, but the private
                keys are not available. E.g. keys exporeted from YubiKeys of maintainers who are not
                present at the time of the repository's creation
            key_name_mappings: A dictionary whose keys are key ids and values are custom names of those keys
        """
        self.metadata_path.mkdir(parents=True)
        self.signer_cache = defaultdict(dict)

        root = Root(consistent_snapshot=False)

        # Snapshot tracks targets and root versions. targets v1 is included by
        # default in snapshot v1. root must be added explicitly.
        sn = Snapshot()
        sn.meta["root.json"] = MetaFile(1)

        public_keys = self._process_keys(signers, additional_verification_keys)

        for role in RolesIterator(roles_keys_data.roles, include_delegations=False):
            if signers.get(role.name) is None:
                raise TAFError(f"Cannot setup role {role.name}. Keys not specified")
            for signer in signers[role.name]:
                key_id = _get_legacy_keyid(signer.public_key)
                self.signer_cache[role.name][key_id] = signer
            for public_key in public_keys[role.name].values():
                key_id = _get_legacy_keyid(public_key)
                if key_id in self.keys_name_mappings:
                    public_key.unrecognized_fields["name"] = self.keys_name_mappings[
                        key_id
                    ]
                root.add_key(public_key, role.name)
            root.roles[role.name].threshold = role.threshold

        targets = Targets(delegations=EmptyDelegations())
        target_roles = {"targets": targets}
        delegations_per_parent: Dict[str, Dict] = defaultdict(dict)
        for role in RolesIterator(roles_keys_data.roles.targets):
            if role.parent is None:
                continue
            parent = role.parent.name
            parent_obj = target_roles.get(parent)
            for signer in signers[role.name]:
                self.signer_cache[role.name][key_id] = signer
            delegated_role = DelegatedRole(
                name=role.name,
                threshold=role.threshold,
                paths=role.paths,
                terminating=role.terminating,
                keyids=list(public_keys[role.name].keys()),
            )
            delegated_metadata = Targets(delegations=EmptyDelegations())
            target_roles[role.name] = delegated_metadata
            delegations_per_parent[parent][role.name] = delegated_role
            sn.meta[f"{role.name}.json"] = MetaFile(1)

        for parent, role_data in delegations_per_parent.items():
            parent_obj = target_roles[parent]
            delegated_keys = {}
            for delegated_role_name in role_data:
                delegated_keys.update(public_keys[delegated_role_name])

            delegations = Delegations(roles=role_data, keys=delegated_keys)
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

    def _process_keys(self, signers, additional_verification_keys):
        public_keys = {}
        for role_name, role_signers in signers.items():
            public_keys[role_name] = {}
            for signer in role_signers:
                key_id = _get_legacy_keyid(signer.public_key)
                public_keys[role_name][key_id] = signer.public_key

        if additional_verification_keys:
            for role_name, keys in additional_verification_keys.items():
                for public_key in keys:
                    key_id = _get_legacy_keyid(public_key)
                    public_keys[role_name][key_id] = public_key
        return public_keys

    def create_delegated_roles(
        self,
        roles_data: List[TargetsRole],
        signers: Dict[str, List[CryptoSigner]],
        additional_verification_keys: Optional[dict] = None,
    ) -> Tuple[List, List]:
        """
        Create a new delegated roles, signes them using the provided signers and
        updates their paren roles.

        Arguments:
            roles_data (list): A list containing data about new roles. Each entry specifies
                            a role's name, path, threshold, and number of signing keys.
            signers (dict): A dictionary that maps each new role to a list of its signers

        Return:
            A list ofroles that were added and a list of roles that already existed
        """
        existing_roles = self.get_all_targets_roles()
        existing_roles.extend(MAIN_ROLES)
        existing_roles = []
        added_roles = []
        roles_parents_dict = defaultdict(list)
        for role_data in roles_data:
            if role_data.name in existing_roles:
                existing_roles.append(role_data.name)
                continue
            if role_data.parent is not None:
                parent = role_data.parent.name
                roles_parents_dict[parent].append(role_data)

        public_keys = self._process_keys(signers, additional_verification_keys)

        for parent, parents_roles_data in roles_parents_dict.items():
            with self.edit(parent) as parent_obj:
                keys_data = {}
                for role_data in parents_roles_data:
                    for public_key in public_keys[role_data.name].values():
                        key_id = _get_legacy_keyid(public_key)
                        keys_data[key_id] = public_key
                        if key_id in self.keys_name_mappings:
                            public_key.unrecognized_fields[
                                "name"
                            ] = self.keys_name_mappings[key_id]

                    for signer in signers[role_data.name]:
                        public_key = signer.public_key
                        key_id = _get_legacy_keyid(public_key)
                        self.signer_cache[role_data.name][key_id] = signer

                    delegated_role = DelegatedRole(
                        name=role_data.name,
                        threshold=role_data.threshold,
                        paths=role_data.paths,
                        terminating=role_data.terminating,
                        keyids=list(keys_data.keys()),
                    )
                    if parent_obj.delegations is None:
                        parent_obj.delegations = Delegations(
                            roles={role_data.name: delegated_role}, keys=keys_data
                        )
                    else:
                        parent_obj.delegations.roles[role_data.name] = delegated_role
                parent_obj.delegations.keys.update(keys_data)

            for role_data in parents_roles_data:
                new_role_signed = Targets(delegations=EmptyDelegations())
                self._set_default_expiration_date(new_role_signed)
                new_role_signed.version = (
                    0  # `close` will bump to initial valid verison 1
                )
                self.close(role_data.name, Metadata(new_role_signed))
                added_roles.append(role_data.name)
        return added_roles, existing_roles

    def create_and_remove_target_files(
        self, added_data: Optional[Dict] = None, removed_data: Optional[Dict] = None
    ) -> Tuple:
        """Create/updates/removes files in the targets directory
        Args:
        - added_data(dict): Dictionary of new data whose keys are target paths of repositories
                            (as specified in targets.json, relative to the targets dictionary).
                            The values are of form:
                            {
                                target: content of the target file
                            }
        - removed_data(dict): Dictionary of the old data whose keys are target paths of
                              repositories
                              (as specified in targets.json, relative to the targets dictionary).
                              The values are not needed. This is just for consistency.

        Content of the target file can be a dictionary, in which case a json file will be created.
        If that is not the case, an ordinary textual file will be created.
        If content is not specified and the file already exists, it will not be modified.
        If it does not exist, an empty file will be created. To replace an existing file with an
        empty file, specify empty content (target: '')

        Returns:
        - Role whose targets were updates
        """
        added_data = {} if added_data is None else added_data
        removed_data = {} if removed_data is None else removed_data
        data = dict(added_data, **removed_data)
        if not data:
            raise TargetsError("Nothing to be modified!")

        added_paths = []
        for path, target_data in added_data.items():
            target_path = (self.targets_path / path).absolute()
            self._create_target_file(target_path, target_data)
            added_paths.append(target_path)

        # remove existing target files
        removed_paths = []
        for path in removed_data.keys():
            target_path = (self.targets_path / path).absolute()
            if target_path.exists():
                if target_path.is_file():
                    target_path.unlink()
                elif target_path.is_dir():
                    shutil.rmtree(target_path, onerror=on_rm_error)
            removed_paths.append(str(path))

        return added_paths, removed_paths

    def _create_target_object(
        self, filesystem_path: str, target_path: str, custom: Optional[Dict]
    ) -> TargetFile:
        """
        Creates a TUF target object, later used to update targets metadata.
        It's first necessary to normalize file line endings (convert all line endings to unix style endings)
        before adding a target objects due to hashes getting calculated differently when using CRLF vs LF line endings.
        So we instead convert all to unix style endings.
        """
        normalize_file_line_endings(filesystem_path)
        data = Path(filesystem_path).read_text().encode()
        target_file = TargetFile.from_data(
            target_file_path=target_path,
            data=data,
            hash_algorithms=["sha256", "sha512"],
        )
        if custom:
            unrecognized_fields = {"custom": custom}
            target_file.unrecognized_fields = unrecognized_fields
        return target_file

    def delete_unregistered_target_files(self, targets_role="targets"):
        """
        Delete all target files not specified in targets.json
        """
        target_files_by_roles = self.sort_roles_targets_for_filenames()
        if targets_role in target_files_by_roles:
            for file_rel_path in target_files_by_roles[targets_role]:
                if file_rel_path not in self.get_targets_of_role(targets_role):
                    (self.targets_path / file_rel_path).unlink()

    def do_timestamp(self, force=False):
        self._snapshot_info.version = self._signed_obj(Snapshot.type).version
        return super().do_timestamp(force)

    def find_delegated_roles_parent(self, delegated_role: str) -> Optional[str]:
        """
        Find parent role of the specified delegated targets role
        """
        parents = ["targets"]

        while parents:
            parent = parents.pop()
            for delegation in self.get_delegations_of_role(parent):
                if delegation == delegated_role:
                    return parent
                parents.append(delegation)
        return None

    def find_parents_of_roles(self, roles: List[str]):
        """
        Find parents of all roles contained by the specified list of roles.
        """
        parents = set()
        for role in roles:
            if role in MAIN_ROLES:
                parents.add("root")
            else:
                parent = self.find_delegated_roles_parent(role)
                if parent is None:
                    raise TAFError(f"Could not determine parent of role {role}")
                parents.add(parent)
        return parents

    def find_role_containing_key_of_role(self, role_name: str) -> Optional[str]:
        if role_name in MAIN_ROLES:
            return Root.type
        parent_roles = list(self.find_parents_of_roles([role_name]))
        if parent_roles:
            return parent_roles[0]
        return None

    def get_delegations_of_role(self, role_name: str) -> Dict:
        """
        Return a dictionary of delegated roles of the specified target role
        """
        signed_obj = self.signed_obj(role_name)
        if signed_obj.delegations:
            return signed_obj.delegations.roles
        return {}

    def get_key_names_of_role(self, role_name: str) -> List:
        keys_name_mapping = self.keys_name_mappings
        key_names = []
        num_of_keys_without_name = 0
        number = len(self.get_keyids_of_role(role_name))
        if keys_name_mapping:
            key_ids = self.get_keyids_of_role(role_name)
            for key_id in key_ids:
                if key_id in keys_name_mapping:
                    key_names.append(keys_name_mapping[key_id])
                else:
                    num_of_keys_without_name += 1
        else:
            num_of_keys_without_name = number

        if not len(key_names) and number == 1:
            return [role_name]

        for num in range(number - num_of_keys_without_name, number):
            key_names.append(f"{role_name}{num + 1}")
        return key_names

    def get_key_ids_of_key_names(self, key_names: List[str]):
        key_name_keys = {}
        reverse_mapping = self.keys_name_mappings_reverse
        for key_name in key_names:
            if key_name in reverse_mapping:
                keyid = reverse_mapping[key_name]
                key_name_keys[key_name] = keyid
        return key_name_keys

    def get_keyids_of_role(self, role_name: str) -> List:
        """
        Return all key ids of the specified role
        """
        role_obj = self._role_obj(role_name)
        return role_obj.keyids

    def get_paths_of_role(self, role_name: str) -> List:
        """
        Return all delegated paths of the specified target role
        """
        parent = self.find_delegated_roles_parent(role_name)
        if parent:
            parent_obj = self.signed_obj(parent)
            return parent_obj.delegations.roles[role_name].paths
        return []

    def get_targets_of_role(self, role_name: str):
        """
        Return all targets of the specified target role
        """
        return self.signed_obj(role_name).targets

    def find_keys_roles(
        self, public_keys: List, check_threshold: Optional[bool] = True
    ) -> List:
        """Find all roles that can be signed by the provided keys.
        A role can be signed by the list of keys if at least the number
        of keys that can sign that file is equal to or greater than the role's
        threshold
        """
        key_ids = [_get_legacy_keyid(public_key) for public_key in public_keys]
        return self.find_keysid_roles(key_ids=key_ids, check_threshold=check_threshold)

    def find_keysid_roles(
        self, key_ids: List, check_threshold: Optional[bool] = True
    ) -> List:
        """Find all roles that can be signed by the provided keys.
        A role can be signed by the list of keys if at least the number
        of keys that can sign that file is equal to or greater than the role's
        threshold
        """
        roles: List[Tuple[str, Optional[str]]] = []
        for role in MAIN_ROLES:
            roles.append((role, None))
        keys_roles = []
        while roles:
            role_name, parent = roles.pop()
            role_obj = self._role_obj(role_name, parent)
            target_roles_key_ids = role_obj.keyids
            threshold = role_obj.threshold
            num_of_signing_keys = len(set(target_roles_key_ids).intersection(key_ids))
            if (
                not check_threshold and num_of_signing_keys >= 1
            ) or num_of_signing_keys >= threshold:
                keys_roles.append(role_name)

            if role_name not in MAIN_ROLES or role_name == "targets":
                for delegation in self.get_delegations_of_role(role_name):
                    roles.append((delegation, role_name))

        return keys_roles

    def find_associated_roles_of_key(self, public_key: SSlibKey) -> List:
        """
        Find all roles whose metadata files can be signed by this key
        Threshold is not important, as long as the key is one of the signing keys
        """
        return self.find_keys_roles([public_key], check_threshold=False)

    def get_all_roles(self) -> List:
        """
        Return a list of all defined roles, main roles combined with delegated targets roles
        """
        all_target_roles = self.get_all_targets_roles()
        all_roles = ["root", "snapshot", "timestamp"] + all_target_roles
        return all_roles

    def get_all_targets_roles(self) -> List:
        """
        Return a list containing names of all target roles
        """
        target_roles = ["targets"]
        all_roles = []
        while target_roles:
            role = target_roles.pop()
            all_roles.append(role)
            for delegation in self.get_delegations_of_role(role):
                target_roles.append(delegation)

        return all_roles

    def get_all_target_files_state(self) -> Tuple:
        """Create dictionaries of added/modified and removed files by comparing current
        file-system state with current signed targets (and delegations) metadata state.

        Args:
        - None
        Returns:
        - Dict of added/modified files and dict of removed target files (inputs for
          `modify_targets` method.)

        Raises:
        - None
        """
        added_target_files: Dict = {}
        removed_target_files: Dict = {}
        # current fs state
        fs_target_files = self.all_target_files()
        # current signed state
        signed_target_files = self.get_signed_target_files()

        # existing files with custom data and (modified) content
        for file_name in fs_target_files:
            target_file = self.targets_path / file_name
            _, hashes = get_file_details(str(target_file))
            # register only new or changed files
            if hashes.get(HASH_FUNCTION) != self.get_target_file_hashes(file_name):
                custom = self.get_target_file_custom_data(file_name)
                added_target_files[file_name] = {
                    "target": target_file.read_text(),
                }
                if custom:
                    added_target_files[file_name]["custom"] = custom

        # removed files
        for file_name in signed_target_files - fs_target_files:
            removed_target_files[file_name] = {}

        return added_target_files, removed_target_files

    def get_expiration_date(self, role: str) -> datetime:
        """
        Return expiration date of the specified role
        """
        meta_file = self.signed_obj(role)
        if meta_file is None:
            raise TAFError(f"Role {role} does not exist")

        date = meta_file.expires
        return date.replace(tzinfo=timezone.utc)

    def get_role_threshold(self, role: str, parent: Optional[str] = None) -> int:
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

    def get_role_paths(self, role):
        """Get paths of the given role

        Args:
        - role(str): TUF role (root, targets, timestamp, snapshot or delegated one)

        Returns:
        Defined delegated paths of delegate target role or * in case of targets
        (the main target is responsible for signing all target files that no delegated role should sign.)

        Raises:
        - TAFError if the role does not exist
        """
        if role == "targets":
            return "*"
        role = self._role_obj(role)
        if role is None:
            raise TAFError(f"Role {role} does not exist")
        return role.paths

    def get_role_from_target_paths(self, target_paths: List) -> Optional[str]:
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

    def get_signable_metadata(self, role: str):
        """Return signable portion of newly generate metadata for given role.

        Args:
        - role(str): TUF role (root, targets, timestamp, snapshot or delegated one)

        Returns:
        A string representing the 'object' encoded in canonical JSON form or None

        Raises:
        None
        """
        signed = self.signed_obj(role)
        return signed.to_dict()

    def get_signed_target_files(self) -> Set[str]:
        """Return all target files signed by all roles.

        Args:
        - None

        Returns:
        - Set of all target paths relative to targets directory
        """
        all_roles = self.get_all_targets_roles()
        return self.get_signed_target_files_of_roles(all_roles)

    def get_signed_target_files_of_roles(
        self, roles: Optional[List] = None
    ) -> Set[str]:
        """Return all target files signed by the specified roles

        Args:
        - roles whose target files will be returned

        Returns:
        - Set of paths of target files of a role relative to targets directory
        """
        if roles is None:
            roles = self.get_all_targets_roles()

        return set(
            reduce(
                operator.iconcat,
                [self.signed_obj(role).targets.keys() for role in roles],
                [],
            )
        )

    def get_signed_targets_with_custom_data(
        self, roles: Optional[List[str]] = None
    ) -> Dict[str, Dict]:
        """Return all target files signed by the specified roles and and their custom data
        as specified in the metadata files

        Args:
        - roles whose target files will be returned

        Returns:
        - A dictionary whose keys are paths target files relative to the targets directory
        and values are custom data dictionaries.
        """
        if roles is None:
            roles = self.get_all_targets_roles()
        target_files: Dict[str, Dict] = {}
        try:
            for role in roles:
                roles_targets = self.get_targets_of_role(role)
                for target_path, target_file in roles_targets.items():
                    target_files.setdefault(target_path, {}).update(
                        target_file.custom or {}
                    )
        except StorageError:
            pass
        return target_files

    def get_target_file_custom_data(self, target_path: str) -> Optional[Dict]:
        """
        Return a custom data of a given target.
        """
        try:
            role = self.get_role_from_target_paths([target_path])
            if role is None:
                return None
            target_obj = self.get_targets_of_role(role).get(target_path)
            if target_obj:
                return target_obj.custom
            return None
        except KeyError:
            raise TAFError(f"Target {target_path} does not exist")

    def get_target_file_hashes(
        self, target_path: str, hash_func: str = HASH_FUNCTION
    ) -> Optional[str]:
        """
        Return hashes of the given target path.

        Raises:
        - TAFError if the target does not exist
        """
        try:
            role = self.get_role_from_target_paths([target_path])
            if role is None:
                return None
            targets_of_role = self.get_targets_of_role(role)
            if target_path not in targets_of_role:
                return None
            hashes = targets_of_role[target_path].hashes
            if hash_func not in hashes:
                raise TAFError(f"Invalid hashing algorithm {hash_func}")
            return hashes[hash_func]
        except KeyError:
            raise TAFError(f"Target {target_path} does not exist")

    def get_key_length_and_scheme_from_metadata(
        self, parent_role: str, keyid: str
    ) -> Tuple:
        """
        Return length and signing scheme of the specified key id.
        This data is specified in metadata files (root or a target role that has delegations)
        """
        try:
            metadata = json.loads(
                Path(
                    self.path, METADATA_DIRECTORY_NAME, f"{parent_role}.json"
                ).read_text()
            )
            metadata = metadata["signed"]
            if "delegations" in metadata:
                metadata = metadata["delegations"]
            scheme = metadata["keys"][keyid]["scheme"]
            pub_key_pem = metadata["keys"][keyid]["keyval"]["public"]
            pub_key = serialization.load_pem_public_key(
                pub_key_pem.encode(), backend=default_backend()
            )
            return pub_key, pub_key_pem, scheme
        except Exception:
            return None, None, None

    def get_key_names_from_metadata(self, parent_role: str) -> Optional[dict]:
        """
        Return key names from metadata files of a parent role (root or a target role that has delegations)
        """
        try:
            metadata = json.loads(
                Path(
                    self.path, METADATA_DIRECTORY_NAME, f"{parent_role}.json"
                ).read_text()
            )
            metadata = metadata["signed"]
            if "delegations" in metadata:
                metadata = metadata["delegations"]

            keys = metadata["keys"]
            names = {
                key_id: key_data["name"]
                for key_id, key_data in keys.items()
                if "name" in key_data
            }
            return names
        except Exception:
            return None

    def get_public_key_of_keyid(self, keyid: str):
        def _find_keyid(role_name, keyid):
            _, pub_key_pem, scheme = self.get_key_length_and_scheme_from_metadata(
                role_name, keyid
            )
            if pub_key_pem is not None:
                return pub_key_pem, scheme

            for delegation in self.get_delegations_of_role(role_name):
                pub_key_pem, scheme = self._find_keyid(delegation, keyid)
                if pub_key_pem is not None:
                    return pub_key_pem, scheme

        _, pub_key_pem, scheme = self.get_key_length_and_scheme_from_metadata(
            "root", keyid
        )
        if pub_key_pem is not None:
            return pub_key_pem, scheme

        targets_obj = self.signed_obj("targets")
        if targets_obj.delegations:
            return _find_keyid("targets", keyid)

    def generate_roles_description(self) -> Dict:
        """
        Generate a roles description dictionary, containing information
        about each role, like its threhold, number of signing keys, delegations
        if it is a target role, key scheme, key lengths.
        """
        roles_description = {}

        def _get_delegations(role_name):
            delegations_info = {}
            for delegation in self.get_delegations_of_role(role_name):
                delegated_role = self._role_obj(delegation)
                delegations_info[delegation] = {
                    "threshold": delegated_role.threshold,
                    "number": len(delegated_role.keyids),
                    "paths": delegated_role.paths,
                    "terminating": delegated_role.terminating,
                }
                pub_key, _, scheme = self.get_key_length_and_scheme_from_metadata(
                    role_name, delegated_role.keyids[0]
                )

                delegations_info[delegation]["scheme"] = scheme
                delegations_info[delegation]["length"] = pub_key.key_size
                delegated_signed = self.signed_obj(delegation)
                if delegated_signed.delegations:
                    inner_roles_data = _get_delegations(delegation)
                    if len(inner_roles_data):
                        delegations_info[delegation]["delegations"] = inner_roles_data
            return delegations_info

        for role_name in MAIN_ROLES:
            role_obj = self._role_obj(role_name)
            roles_description[role_name] = {
                "threshold": role_obj.threshold,
                "number": len(role_obj.keyids),
            }
            pub_key, _, scheme = self.get_key_length_and_scheme_from_metadata(
                "root", role_obj.keyids[0]
            )
            roles_description[role_name]["scheme"] = scheme
            roles_description[role_name]["length"] = pub_key.key_size
            if role_name == "targets":
                targets_signed = self.signed_obj(role_name)
                if targets_signed.delegations:
                    delegations_info = _get_delegations(role_name)
                    if len(delegations_info):
                        roles_description[role_name]["delegations"] = delegations_info
        return {"roles": roles_description}

    def get_role_keys(self, role):
        """Get keyids of the given role

        Args:
        - role(str): TUF role (root, targets, timestamp, snapshot or delegated one)

        Returns:
            List of the role's keyids (i.e., keyids of the keys).

        """
        role_obj = self._role_obj(role)
        if role_obj is None:
            return None
        try:
            return role_obj.keyids
        except KeyError:
            pass

    def is_valid_metadata_key(
        self, role: str, key: Union[SSlibKey, str], scheme=DEFAULT_RSA_SIGNATURE_SCHEME
    ) -> bool:
        """Checks if metadata role contains key id of provided key.

        Args:
        - role(str): TUF role (root, targets, timestamp, snapshot or delegated one)
        - key(securesystemslib.formats.RSAKEY_SCHEMA): Role's key.

        Returns:
        Boolean. True if key id is in metadata role key ids, False otherwise.

        Raises:
        - TAFError if key is not valid
        """

        try:
            if isinstance(key, str):
                # mypy will complain if we redefine key
                ssl_lib_key = get_sslib_key_from_value(key, scheme)
            else:
                ssl_lib_key = key
            key_id = _get_legacy_keyid(ssl_lib_key)
        except Exception:
            # TODO log
            raise TAFError("Invalid public key specified")
        else:
            return key_id in self.get_keyids_of_role(role)

    def is_valid_metadata_yubikey(self, role: str, public_key=None) -> bool:
        """Checks if metadata role contains key id from YubiKey.

        Args:
        - role(str): TUF role (root, targets, timestamp, snapshot or delegated one
        - public_key(securesystemslib.formats.RSAKEY_SCHEMA): RSA public key dict

        Returns:
        Boolean. True if smart card key id belongs to metadata role key ids

        Raises:
        - YubikeyError
        """

        if public_key is None:
            public_key = yk.get_piv_public_key_tuf()

        return self.is_valid_metadata_key(role, public_key)

    def _load_role_signers(self, role: str, signers: List) -> None:
        """Verify that the signers can be used to sign the specified role and
        add them to the signer cache

        Args:
        - role(str): TUF role (root, targets, timestamp, snapshot or delegated one)
        - signers: A list of signers

        Returns:
        None

        Raises:
        - InvalidKeyError: If metadata cannot be signed with given key.
        """

        for signer in signers:
            key = signer.public_key
            if not self.is_valid_metadata_key(role, key):
                raise InvalidKeyError(role)
            self.signer_cache[role][key.keyid] = signer

    def map_signing_roles(self, target_filenames: List) -> Dict:
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

            for delegation in self.get_delegations_of_role(role):
                roles.append(delegation)

        return roles_targets

    def modify_targets(
        self, added_data: Optional[Dict] = None, removed_data: Optional[Dict] = None
    ) -> Targets:
        """Creates a target.json file containing a repository's commit for each repository.
        Adds those files to the tuf repository.

        Args:
        - added_data(dict): Dictionary of new data whose keys are target paths of repositories
                            (as specified in targets.json, relative to the targets dictionary).
                            The values are of form:
                            {
                                target: content of the target file
                                custom: {
                                    custom_field1: custom_value1,
                                    custom_field2: custom_value2
                                }
                            }
        - removed_data(dict): Dictionary of the old data whose keys are target paths of
                              repositories
                              (as specified in targets.json, relative to the targets dictionary).
                              The values are not needed. This is just for consistency.

        Content of the target file can be a dictionary, in which case a json file will be created.
        If that is not the case, an ordinary textual file will be created.
        If content is not specified and the file already exists, it will not be modified.
        If it does not exist, an empty file will be created. To replace an existing file with an
        empty file, specify empty content (target: '')

        Custom is an optional property which, if present, will be used to specify a TUF target's

        Returns:
        - Role whose targets were updates
        """
        added_data = {} if added_data is None else added_data
        removed_data = {} if removed_data is None else removed_data
        data = dict(added_data, **removed_data)
        if not data:
            raise TargetsError("Nothing to be modified!")

        target_paths = list(data.keys())
        targets_role = self.get_role_from_target_paths(target_paths)
        if targets_role is None:
            raise TargetsError(
                f"Could not find a common role for target paths:\n{'-'.join(target_paths)}"
            )
        _, removed_paths = self.create_and_remove_target_files(added_data, removed_data)

        target_files = []
        for path, target_data in added_data.items():
            target_path = (self.targets_path / path).absolute()
            custom = target_data.get("custom", None)
            target_file = self._create_target_object(target_path, path, custom)
            target_files.append(target_file)

        targets_role = self._modify_targets_role(
            target_files, removed_paths, targets_role
        )
        return targets_role

    def load_key_names(self):
        def _get_keys_of_delegations(role_name):
            keys = {}
            role_keys = self.get_key_names_from_metadata(role_name)
            if role_keys is not None:
                keys.update(role_keys)

            for delegation in self.get_delegations_of_role(role_name):
                delegated_signed = self.signed_obj(delegation)
                if delegated_signed.delegations:
                    inner_roles_keys = _get_keys_of_delegations(delegation)
                    if inner_roles_keys:
                        keys.update(inner_roles_keys)
            return keys

        root_metadata = self.signed_obj("root")
        name_mapping = {}
        keys = root_metadata.keys
        for key_id, key_obj in keys.items():
            name_data = key_obj.unrecognized_fields
            if name_data is not None and "name" in name_data:
                name_mapping[key_id] = name_data["name"]
        name_mapping.update(_get_keys_of_delegations("targets"))
        return name_mapping

    def _modify_targets_role(
        self,
        added_target_files: List[TargetFile],
        removed_paths: List[str],
        role_name: Optional[str] = Targets.type,
    ) -> Targets:
        """Add target files to top-level targets metadata."""
        with self.edit_targets(rolename=role_name) as targets:
            for target_file in added_target_files:
                targets.targets[target_file.path] = target_file
            for path in removed_paths:
                targets.targets.pop(path, None)
        return targets

    def revoke_metadata_key(self, key_id: str, roles: Optional[List[str]] = None):
        """Remove metadata key of the provided role without updating timestamp and snapshot.

        Args:
        - role(str): TUF role (root, targets, timestamp, snapshot or delegated one)
        - key_id(str): An object conformant to 'securesystemslib.formats.KEYID_SCHEMA'.

        Returns:
            removed_from_roles, not_added_roles, less_than_threshold_roles
        """
        if key_id is None:
            raise TAFError("Keyid to revoke not specified")
        if not roles:
            roles = self.find_keysid_roles([key_id])

        if not roles:
            raise TAFError("Key not used to sign any role")

        parents = self.find_parents_of_roles(roles)
        self.verify_signers_loaded(parents)

        removed_from_roles = []
        not_added_roles = []
        less_than_threshold_roles = []

        def _check_if_can_remove(key_id, role):
            role_obj = self._role_obj(role)
            if len(role_obj.keyids) - 1 < role_obj.threshold:
                less_than_threshold_roles.append(role)
                return False
            key_ids_of_role = self.get_keyids_of_role(role) or []
            if key_id not in key_ids_of_role:
                not_added_roles.append(role)
                return False
            return True

        main_roles = [
            role
            for role in roles
            if role in MAIN_ROLES and _check_if_can_remove(key_id, role)
        ]
        if len(main_roles):
            with self.edit_root() as root:
                for role in main_roles:
                    root.revoke_key(keyid=key_id, role=role)
                    removed_from_roles.append(role)

        roles_by_parents = defaultdict(list)
        delegated_roles = [
            role
            for role in roles
            if role not in MAIN_ROLES and _check_if_can_remove(key_id, role)
        ]
        if len(delegated_roles):
            for role in delegated_roles:
                parent = self.find_delegated_roles_parent(role)
                roles_by_parents[parent].append(role)

            for parent, roles_of_parent in roles_by_parents.items():
                with self.edit(parent) as parent_role:
                    for role in roles_of_parent:
                        parent_role.revoke_key(keyid=key_id, role=role)
                        removed_from_roles.append(role)

        return removed_from_roles, not_added_roles, less_than_threshold_roles

    def remove_delegated_paths(self, roles_paths: Dict[str, List[str]]):
        """
        Remove delegated paths to delegated role and return True if at least one removed
        """

        updated = False
        for role, paths in roles_paths.items():

            if not self.check_if_role_exists(role):
                raise TAFError(f"Role {role} does not exist")

            parent_role = self.find_delegated_roles_parent(role)
            if parent_role is None:
                raise TAFError(f"Role {role} is not a delegated role")

            self.verify_signers_loaded([parent_role])
            with self.edit(parent_role) as parent:
                for path in paths:
                    if path in parent.delegations.roles[role].paths:
                        parent.delegations.roles[role].paths.remove(path)
                        updated = True
        return updated

    def remove_from_open_metadata(self, roles: List[str]) -> None:
        """
        Removes the listed roles from metadata_to_keep_open list
        """
        for role in roles:
            if role in self._metadata_to_keep_open:
                self._metadata_to_keep_open.remove(role)

    def roles_targets_for_filenames(self, target_filenames):
        """Sort target files by roles
        Args:
        - target_filenames: List of relative paths of target files
        Returns:
        - A dictionary mapping roles to a list of target files belonging
          to the provided target_filenames list delegated to the role
        """
        targets_roles_mapping = self.map_signing_roles(target_filenames)
        roles_targets_mapping = {}
        for target_filename, role_name in targets_roles_mapping.items():
            roles_targets_mapping.setdefault(role_name, []).append(target_filename)
        return roles_targets_mapping

    def _role_obj(self, role: str, parent: Optional[str] = None):
        """
        Return TUF's role object for the specified role
        """
        if role in MAIN_ROLES:
            md = self.open("root")
            try:
                data = md.to_dict()["signed"]["roles"][role]
                return Role.from_dict(data)
            except (KeyError, ValueError):
                raise TAFError("root.json is invalid")
        else:
            parent_name = self.find_delegated_roles_parent(role)
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

    def signed_obj(self, role: str):
        """
        Return TUF's signed object for the specified role
        """
        md = self.open(role)
        return self._signed_obj(role, md)

    def _signed_obj(self, role: str, md=None):
        if md is None:
            md = self.open(role)
        try:
            signed_data = md.to_dict()["signed"]
            role_to_role_class = {
                "root": Root,
                "targets": Targets,
                "snapshot": Snapshot,
                "timestamp": Timestamp,
            }
            role_class = role_to_role_class.get(role, Targets)
            return role_class.from_dict(signed_data)
        except (KeyError, ValueError):
            raise TAFError(f"Invalid metadata file {role}.json")

    def _set_default_expiration_date(self, signed: Signed) -> None:
        """
        Update expiration dates of the specified signed object
        """
        interval = self.expiration_intervals.get(signed.type, 90)
        start_date = datetime.now(timezone.utc)
        expiration_date = start_date + timedelta(days=interval)
        signed.expires = expiration_date

    def set_metadata_expiration_date(
        self,
        role_name: str,
        start_date: Optional[datetime] = None,
        interval: Optional[int] = None,
    ) -> None:
        """Set expiration date of the provided role.

        Args:
        - role(str): TUF role (root, targets, timestamp, snapshot or delegated one)
        - start_date(datetime): Date to which the specified interval is added when calculating
                                expiration date. If a value is not provided, it is set to the
                                current time.
        - signers(List[CryptoSigner]): a list of signers
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
        self.verify_signers_loaded([role_name])
        with self.edit(role_name) as role:
            start_date = datetime.now(timezone.utc)
            if interval is None:
                try:
                    interval = self.expiration_intervals[role_name]
                except KeyError:
                    interval = self.expiration_intervals["targets"]
            expiration_date = start_date + timedelta(days=interval)
            role.expires = expiration_date

    def sort_roles_targets_for_filenames(self):
        """
        Group target files per target roles
        """
        rel_paths = []
        for filepath in self.targets_path.rglob("*"):
            if filepath.is_file():
                file_rel_path = str(
                    Path(filepath).relative_to(self.targets_path).as_posix()
                )
                rel_paths.append(file_rel_path)

        files_to_roles = self.map_signing_roles(rel_paths)
        roles_targets = {}
        for target_file, role in files_to_roles.items():
            roles_targets.setdefault(role, []).append(target_file)
        return roles_targets

    def set_key_names(self, new_key_names):
        parent_roles_keys = defaultdict(list)
        for key_id, key_name in new_key_names.items():
            roles_of_key = self.find_keysid_roles([key_id], check_threshold=False)
            for role in roles_of_key:
                role_containing_key = self.find_role_containing_key_of_role(role)
                parent_roles_keys[role_containing_key].append((key_id, key_name, role))
                self.add_key_name(key_name, key_id, overwrite=True)

        for role_name, keys_data in parent_roles_keys.items():
            with self.edit(role_name) as role_obj:
                for key_data in keys_data:
                    key_id, key_name, keys_role = key_data
                    role_obj.revoke_key(key_id, keys_role)
                    public_key_pem, _ = self.get_public_key_of_keyid(key_id)
                    public_key = get_sslib_key_from_value(public_key_pem)
                    public_key.unrecognized_fields["name"] = key_name
                    role_obj.add_key(public_key, keys_role)

    def sync_snapshot_with_roles(self, roles: List[str]) -> None:
        """
        Add versions of newly created target roles to the snapshot.
        Also update the versions of their parent roles, which are modified
        when a new delegated role is added.
        """
        with self.edit(Snapshot.type) as sn:
            for role in roles:
                sn.meta[f"{role}.json"].version = sn.meta[f"{role}.json"].version + 1

    def update_target_role(self, role: str, target_paths: Dict, force=False):
        """
        Update the specified target role by adding or removing
        target files and target objects for the specified target paths
        If false is True, update the metadata files even if no target
        paths are specified
        """
        if not self.check_if_role_exists(role):
            raise TAFError(f"Role {role} does not exist")
        self.verify_signers_loaded([role])
        removed_paths = []
        target_files = []
        if target_paths:
            for target_path in target_paths:
                full_path = self.path / TARGETS_DIRECTORY_NAME / target_path
                # file removed, removed from te role
                if not full_path.is_file():
                    removed_paths.append(target_path)
                else:
                    custom_data = self.get_target_file_custom_data(target_path)
                    target_file = self._create_target_object(
                        full_path, target_path, custom_data
                    )
                    target_files.append(target_file)

            self._modify_targets_role(target_files, removed_paths, role)
        elif force:
            with self.edit(role) as _:
                pass

    def update_snapshot_and_timestamp(self, force: Optional[bool] = True):
        """
        Update timestamp and snapshot roles. If force is true, update them
        even if their content was not modified
        """
        self.verify_signers_loaded(["snapshot", "timestamp"])
        self.do_snapshot(force=force)
        self.do_timestamp(force=force)

    def verify_roles_exist(self, roles: List[str]):
        """
        Check if the specified roles exist and raise an error if an least one does not exist
        """
        non_existant_roles = []
        for role in roles:
            if not self.check_if_role_exists(role):
                non_existant_roles.append(role)
        if len(non_existant_roles):
            raise TAFError(f"Role(s) {', '.join(non_existant_roles)} do not exist")

    def verify_signers_loaded(self, roles: List[str]):
        """
        Verify that the signers associated with the specified keys were added to the signer cache.
        Raise an error if that is not the case
        """
        not_loaded = [role for role in roles if role not in self.signer_cache]
        if len(not_loaded):
            raise SignersNotLoaded(roles=not_loaded)
