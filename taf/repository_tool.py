import datetime
import json
import operator
import os
import shutil
from fnmatch import fnmatch
from functools import partial, reduce
from pathlib import Path

import securesystemslib
import tuf.roledb
from securesystemslib.exceptions import Error as SSLibError, RepositoryError
from securesystemslib.interface import import_rsa_privatekey_from_file
from securesystemslib.util import HASH_FUNCTION, get_file_details
from tuf.exceptions import Error as TUFError
from tuf.repository_tool import (
    METADATA_DIRECTORY_NAME,
    TARGETS_DIRECTORY_NAME,
    import_rsakey_from_pem,
    load_repository,
)
from tuf.roledb import get_roleinfo

from taf import YubikeyMissingLibrary
from taf.constants import DEFAULT_RSA_SIGNATURE_SCHEME
from taf.exceptions import (
    InvalidKeyError,
    MetadataUpdateError,
    RootMetadataUpdateError,
    SigningError,
    SnapshotMetadataUpdateError,
    TargetsError,
    TargetsMetadataUpdateError,
    TimestampMetadataUpdateError,
    YubikeyError,
    InvalidRepositoryError,
)
from taf.git import GitRepository
from taf.utils import normalize_file_line_endings, on_rm_error

try:
    import taf.yubikey as yk
except ImportError:
    yk = YubikeyMissingLibrary()

# Default expiration intervals per role
expiration_intervals = {"root": 365, "targets": 90, "snapshot": 7, "timestamp": 1}

# Loaded keys cache
role_keys_cache = {}


DISABLE_KEYS_CACHING = False


def get_role_metadata_path(role):
    return f"{METADATA_DIRECTORY_NAME}/{role}.json"


def get_target_path(target_name):
    return f"{TARGETS_DIRECTORY_NAME}/{target_name}"


def is_delegated_role(role):
    return role not in ("root", "targets", "snapshot", "timestamp")


def load_role_key(keystore, role, password=None, scheme=DEFAULT_RSA_SIGNATURE_SCHEME):
    """Loads the specified role's key from a keystore file.
    The keystore file can, but doesn't have to be password protected.

    NOTE: Keys inside keystore should match a role name!

    Args:
        - keystore(str): Path to the keystore directory
        - role(str): TUF role (root, targets, timestamp, snapshot or delegated one)
        - password(str): (Optional) password used for PEM decryption
        - scheme(str): A signature scheme used for signing.

    Returns:
        - An RSA key object, conformant to 'securesystemslib.RSAKEY_SCHEMA'.

    Raises:
        - securesystemslib.exceptions.FormatError: If the arguments are improperly formatted.
        - securesystemslib.exceptions.CryptoError: If path is not a valid encrypted key file.
    """
    if not password:
        password = None
    key = role_keys_cache.get(role)
    if key is None:
        if password is not None:
            key = import_rsa_privatekey_from_file(
                str(Path(keystore, role)), password, scheme=scheme
            )
        else:
            key = import_rsa_privatekey_from_file(
                str(Path(keystore, role)), scheme=scheme
            )
    if not DISABLE_KEYS_CACHING:
        role_keys_cache[role] = key
    return key


def root_signature_provider(signature_dict, key_id, _key, _data):
    """Root signature provider used to return signatures created remotely.

    Args:
        - signature_dict(dict): Dict where key is key_id and value is signature
        - key_id(str): Key id from targets metadata file
        - _key(securesystemslib.formats.RSAKEY_SCHEMA): Key info
        - _data(dict): Data to sign (already signed remotely)

    Returns:
        Dictionary that comforms to `securesystemslib.formats.SIGNATURE_SCHEMA`

    Raises:
        - KeyError: If signature for key_id is not present in signature_dict
    """
    from binascii import hexlify

    return {"keyid": key_id, "sig": hexlify(signature_dict.get(key_id)).decode()}


def yubikey_signature_provider(name, key_id, key, data):  # pylint: disable=W0613
    """
    A signatures provider which asks the user to insert a yubikey
    Useful if several yubikeys need to be used at the same time
    """
    from binascii import hexlify

    data = securesystemslib.formats.encode_canonical(data).encode("utf-8")

    def _check_key_and_get_pin(expected_key_id):
        try:
            inserted_key = yk.get_piv_public_key_tuf()
            if expected_key_id != inserted_key["keyid"]:
                return None
            serial_num = yk.get_serial_num(inserted_key)
            pin = yk.get_key_pin(serial_num)
            if pin is None:
                pin = yk.get_and_validate_pin(name)
            return pin
        except Exception:
            return None

    while True:
        # check if the needed YubiKey is inserted before asking the user to do so
        # this allows us to use this signature provider inside an automated process
        # assuming that all YubiKeys needed for signing are inserted
        pin = _check_key_and_get_pin(key_id)
        if pin is not None:
            break
        input(f"Insert {name} and press enter")

    signature = yk.sign_piv_rsa_pkcs1v15(data, pin)
    return {"keyid": key_id, "sig": hexlify(signature).decode()}


class Repository:
    def __init__(self, path, repo_name="default"):
        self._path = Path(path)
        self.name = repo_name

    _framework_files = ["repositories.json", "test-auth-repo"]

    @property
    def path(self):
        return str(self._path)

    @property
    def targets_path(self):
        return self._path / TARGETS_DIRECTORY_NAME

    @property
    def metadata_path(self):
        return self._path / METADATA_DIRECTORY_NAME

    _tuf_repository = None

    @property
    def _repository(self):
        if self._tuf_repository is None:
            self._load_tuf_repository(self.path)
        return self._tuf_repository

    @property
    def repo_id(self):
        return GitRepository(self.path).initial_commit

    @property
    def certs_dir(self):
        certs_dir = self._path / "certs"
        certs_dir.mkdir(parents=True, exist_ok=True)
        return str(certs_dir)

    def _add_delegated_key(
        self, role, keyid, pub_key, keytype="rsa", scheme=DEFAULT_RSA_SIGNATURE_SCHEME
    ):
        """
        Adds public key of a new delegated role to the list of all keys of
        delegated roles.
        Args:
        - role (str): parent target role's name
        - keyid (str): keyid of the new signing key
        - pub_key(str): public component of the new signing key
        - keytype (str): key's type
        - sheme (str): signature scheme
        """
        roleinfo = tuf.roledb.get_roleinfo(role, self.name)
        keysinfo = roleinfo["delegations"]["keys"]
        if keyid in keysinfo:
            return
        key = {"public": pub_key.strip()}
        key_metadata_format = securesystemslib.keys.format_keyval_to_metadata(
            keytype, scheme, key
        )
        keysinfo[keyid] = key_metadata_format
        tuf.roledb.update_roleinfo(role, roleinfo, repository_name=self.name)

    def _add_target(self, targets_obj, file_path, custom=None):
        """
        <Purpose>
        Normalizes line endings (converts all line endings to unix style endings) and
        registers the target file as a TUF target
        <Arguments>
        targets_obj: TUF targets objects (instance of TUF's targets role class)
        file_path: full path of the target file
        custom: custom target data
        """
        file_path = str(Path(file_path).absolute())
        normalize_file_line_endings(file_path)
        targets_obj.add_target(file_path, custom)

    def add_metadata_key(self, role, pub_key_pem, scheme=DEFAULT_RSA_SIGNATURE_SCHEME):
        """Add metadata key of the provided role.

        Args:
        - role(str): TUF role (root, targets, timestamp, snapshot or delegated one)
        - pub_key_pem(str|bytes): Public key in PEM format

        Returns:
        None

        Raises:
        - securesystemslib.exceptions.FormatError: If the arguments are improperly formatted.
        - securesystemslib.exceptions.UnknownRoleError: If 'rolename' has not been delegated by this
                                                        targets object.
        - securesystemslib.exceptions.UnknownKeyError: If 'key_id' is not found in the keydb database.

        """
        if isinstance(pub_key_pem, bytes):
            pub_key_pem = pub_key_pem.decode("utf-8")

        if is_delegated_role(role):
            parent_role = self.find_delegated_roles_parent(role)
            tuf.roledb._roledb_dict[self.name][role]["keyids"] = self.get_role_keys(
                role, parent_role
            )

        key = import_rsakey_from_pem(pub_key_pem, scheme)
        self._role_obj(role).add_verification_key(key)

        if is_delegated_role(role):
            keyids = tuf.roledb.get_roleinfo(role, self.name)["keyids"]
            self.set_delegated_role_property("keyids", role, keyids, parent_role)
            self._add_delegated_key(parent_role, keyids[-1], pub_key_pem, scheme=scheme)

    def _load_tuf_repository(self, path):
        """
        Load tuf repository. Should only be called directly if a different set of metadata files
        should be loaded (and not the one located at repo path/metadata)
        """
        # before attempting to tuf repository, create empty targets directory if it does not exist
        # to avoid errors raised by tuf
        if not self.targets_path.is_dir():
            self.targets_path.mkdir(parents=True, exist_ok=True)
        try:
            self._tuf_repository = load_repository(path, self.name)
        except RepositoryError:
            raise InvalidRepositoryError(f"{self.name} is not a valid TUF repository!")

    def reload_tuf_repository(self):
        """
        Reload tuf repository. Should be called after content on the disk is called.
        """
        tuf.roledb.remove_roledb(self.name)
        self._load_tuf_repository(self.path)

    def _role_obj(self, role):
        """Helper function for getting TUF's role object, given the role's name

        Args:
        - role(str): TUF role (root, targets, timestamp, snapshot or delegated one)

        Returns:
        One of metadata objects:
            Root, Snapshot, Timestamp, Targets or delegated metadata

        Raises:
        - securesystemslib.exceptions.FormatError: If the arguments are improperly formatted.
        - securesystemslib.exceptions.UnknownRoleError: If 'rolename' has not been delegated by this
                                                        targets object.
        """
        if role == "targets":
            return self._repository.targets
        elif role == "snapshot":
            return self._repository.snapshot
        elif role == "timestamp":
            return self._repository.timestamp
        elif role == "root":
            return self._repository.root
        return self._repository.targets(role)

    def _try_load_metadata_key(self, role, key):
        """Check if given key can be used to sign given role and load it.

        Args:
        - role(str): TUF role (root, targets, timestamp, snapshot or delegated one)
        - key(securesystemslib.formats.RSAKEY_SCHEMA): Private key used to sign metadata

        Returns:
        None

        Raises:
        - securesystemslib.exceptions.FormatError: If the arguments are improperly formatted.
        - securesystemslib.exceptions.UnknownRoleError: If 'rolename' has not been delegated by this
                                                        targets object.
        - InvalidKeyError: If metadata cannot be signed with given key.
        """
        if not self.is_valid_metadata_key(role, key):
            raise InvalidKeyError(role)
        self._role_obj(role).load_signing_key(key)

    def add_existing_target(self, file_path, targets_role="targets", custom=None):
        """Registers new target files with TUF.
        The files are expected to be inside the targets directory.

        Args:
        - file_path(str): Path to target file
        - targets_role(str): Targets or delegated role: a targets role (the root targets role
                            or one of the delegated ones)
        - custom(dict): Custom information for given file

        Returns:
        None

        Raises:
        - securesystemslib.exceptions.FormatError: If 'filepath' is improperly formatted.
        - securesystemslib.exceptions.Error: If 'filepath' is not located in the repository's targets
                                            directory.
        """
        targets_obj = self._role_obj(targets_role)
        self._add_target(targets_obj, file_path, custom)

    def get_all_target_files_state(self):
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
        added_target_files = {}
        removed_target_files = {}

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
                added_target_files[file_name] = {
                    "target": target_file.read_text(),
                    "custom": self.get_target_file_custom_data(file_name),
                }

        # removed files
        for file_name in signed_target_files - fs_target_files:
            removed_target_files[file_name] = {}

        return added_target_files, removed_target_files

    def get_signed_target_files(self):
        """Return all target files signed by all roles.

        Args:
        - None

        Returns:
        - Set of all target paths relative to targets directory
        """
        all_roles = self.get_all_targets_roles()
        return self.get_singed_target_files_of_roles(all_roles)

    def get_singed_target_files_of_roles(self, roles):
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
                [self._role_obj(role).target_files for role in roles],
                [],
            )
        )

    def get_singed_targets_with_custom_data(self, roles):
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

    def modify_targets(self, added_data=None, removed_data=None):
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
        - Role name used to update given targets
        """
        added_data = {} if added_data is None else added_data
        removed_data = {} if removed_data is None else removed_data
        data = dict(added_data, **removed_data)
        if not data:
            raise TargetsError("Nothing to be modified!")

        target_paths = list(data.keys())
        targets_role = self.get_role_from_target_paths(data)
        if targets_role is None:
            raise TargetsError(
                f"Could not find a common role for target paths:\n{'-'.join(target_paths)}"
            )
        targets_obj = self._role_obj(targets_role)
        # add new target files
        for path, target_data in added_data.items():
            target_path = (self.targets_path / path).absolute()
            self._create_target_file(target_path, target_data)
            custom = target_data.get("custom", None)
            self._add_target(targets_obj, str(target_path), custom)

        # remove existing target files
        for path in removed_data.keys():
            target_path = (self.targets_path / path).absolute()
            if target_path.exists():
                if target_path.is_file():
                    target_path.unlink()
                elif target_path.is_dir():
                    shutil.rmtree(target_path, onerror=on_rm_error)

            try:
                targets_obj.remove_target(path)
            except Exception:
                continue

        return targets_role

    def all_target_files(self):
        """
        Return a set of relative paths of all files inside the targets
        directory
        """
        targets = []
        for root, _, filenames in os.walk(str(self.targets_path)):
            for filename in filenames:
                filepath = Path(root) / filename
                if filepath.is_file():
                    targets.append(
                        str(
                            Path(
                                os.path.relpath(str(filepath), str(self.targets_path))
                            ).as_posix()
                        )
                    )
        return set(targets)

    def get_target_file_custom_data(self, target_path):
        """
        Return a custom data of a given target.
        """
        try:
            role = self.get_role_from_target_paths([target_path])
            roleinfo = get_roleinfo(role)
            return roleinfo["paths"][target_path]
        except Exception:
            return None

    def get_target_file_hashes(self, target_path, hash_func=HASH_FUNCTION):
        """
        Return hashes of a given target path.
        """
        hashes = {"sha256": None, "sha512": None}
        try:
            role = self.get_role_from_target_paths([target_path])
            role_dict = json.loads((self.metadata_path / f"{role}.json").read_text())
            hashes.update(role_dict["signed"]["targets"][target_path]["hashes"])
        except Exception:
            pass

        return hashes.get(hash_func, hashes)

    def get_role_from_target_paths(self, target_paths):
        """
        Find a common role that could be used to sign given target paths.

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

    def _collect_target_paths_of_role(self, target_roles_paths):
        all_target_relpaths = []
        for target_role_path in target_roles_paths:
            try:
                if (self.targets_path / target_role_path).is_file():
                    all_target_relpaths.append(target_role_path)
                    continue
            except OSError:
                pass
            for filepath in self.targets_path.rglob(target_role_path):
                if filepath.is_file():
                    file_rel_path = str(
                        Path(filepath).relative_to(self.targets_path).as_posix()
                    )
                    all_target_relpaths.append(file_rel_path)
        return all_target_relpaths

    def _create_target_file(self, target_path, target_data):
        # if the target's parent directory should not be "targets", create
        # its parent directories if they do not exist
        target_dir = target_path.parents[0]
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

    def delete_unregistered_target_files(self, targets_role="targets"):
        """
        Delete all target files not specified in targets.json
        """
        targets_obj = self._role_obj(targets_role)
        target_files_by_roles = self.sort_roles_targets_for_filenames()
        if targets_role in target_files_by_roles:
            for file_rel_path in target_files_by_roles[targets_role]:
                if file_rel_path not in targets_obj.target_files:
                    (self.targets_path / file_rel_path).unlink()

    def find_delegated_roles_parent(self, role_name):
        """
        A simple implementation of finding a delegated targets role's parent
        assuming that every delegated role is delegated by just one role
        and that there won't be many delegations.
        Args:
            - role_name: Role

        Returns:
            Parent role's name
        """

        def _find_delegated_role(parent_role_name, role_name):
            delegations = self.get_delegations_info(parent_role_name)
            if len(delegations):
                for role_info in delegations.get("roles"):
                    # check if this role can sign target_path
                    delegated_role_name = role_info["name"]
                    if delegated_role_name == role_name:
                        return parent_role_name
                    parent = _find_delegated_role(delegated_role_name, role_name)
                    if parent is not None:
                        return parent
            return None

        return _find_delegated_role("targets", role_name)

    def find_keys_roles(self, public_keys):
        """Find all roles that can be signed by the provided keys.
        A role can be signed by the list of keys if at least the number
        of keys that can sign that file is equal to or greater than the role's
        threshold
        """

        def _map_keys_to_roles(role_name, key_ids):
            keys_roles = []
            delegations = self.get_delegations_info(role_name)
            if len(delegations):
                for role_info in delegations.get("roles"):
                    # check if this role can sign target_path
                    delegated_role_name = role_info["name"]
                    delegated_roles_keyids = role_info["keyids"]
                    delegated_roles_threshold = role_info["threshold"]
                    num_of_signing_keys = len(
                        set(delegated_roles_keyids).intersection(key_ids)
                    )
                    if num_of_signing_keys >= delegated_roles_threshold:
                        keys_roles.append(delegated_role_name)
                    keys_roles.extend(_map_keys_to_roles(delegated_role_name, key_ids))
            return keys_roles

        keyids = [key["keyid"] for key in public_keys]
        return _map_keys_to_roles("targets", keyids)

    def get_all_targets_roles(self):
        """
        Return a list containing names of all target roles
        """

        def _traverse_targets_roles(role_name):
            roles = [role_name]
            delegations = self.get_delegations_info(role_name)
            if len(delegations):
                for role_info in delegations.get("roles"):
                    # check if this role can sign target_path
                    delegated_role_name = role_info["name"]
                    roles.extend(_traverse_targets_roles(delegated_role_name))
            return roles

        return _traverse_targets_roles("targets")

    def get_delegated_role_property(self, property_name, role_name, parent_role=None):
        """
        Extract value of the specified property of the provided delegated role from
        its parent's role info.
        Args:
            - property_name: Name of the property (like threshold)
            - role_name: Role
            - parent_role: Parent role

        Returns:
            The specified property's value
        """
        # TUF raises an error when asking for properties like threshold and signing keys
        # of a delegated role (see https://github.com/theupdateframework/tuf/issues/574)
        # The following workaround presumes that one every delegated role is a deegation
        # of exactly one delegated role
        if parent_role is None:
            parent_role = self.find_delegated_roles_parent(role_name)
        delegations = self.get_delegations_info(parent_role)
        for delegated_role in delegations["roles"]:
            if delegated_role["name"] == role_name:
                return delegated_role[property_name]
        return None

    def get_expiration_date(self, role):
        return self._role_obj(role).expiration

    def get_role_keys(self, role, parent_role=None):
        """Get keyids of the given role

        Args:
        - role(str): TUF role (root, targets, timestamp, snapshot or delegated one)
        - parent_role(str): Name of the parent role of the delegated role. If not specified,
                            it will be set automatically, but this might be slow if there
                            are many delegations.

        Returns:
        List of the role's keyids (i.e., keyids of the keys).

        Raises:
        - securesystemslib.exceptions.FormatError: If the arguments are improperly formatted.
        - securesystemslib.exceptions.UnknownRoleError: If 'rolename' has not been delegated by this
                                                        targets object.
        """
        role_obj = self._role_obj(role)
        if role_obj is None:
            return None
        try:
            return role_obj.keys
        except KeyError:
            pass
        return self.get_delegated_role_property("keyids", role, parent_role)

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
        return self.get_delegated_role_property("paths", role, parent_role)

    def get_role_repositories(self, role, parent_role=None):
        """Get repositories of the given role

        Args:
        - role(str): TUF role (root, targets, timestamp, snapshot or delegated one)
        - parent_role(str): Name of the parent role of the delegated role. If not specified,
                            it will be set automatically, but this might be slow if there
                            are many delegations.

        Returns:
        Repositories' path from repositories.json that matches given role paths

        Raises:
        - securesystemslib.exceptions.FormatError: If the arguments are improperly formatted.
        - securesystemslib.exceptions.UnknownRoleError: If 'rolename' has not been delegated by this
        """
        role_paths = self.get_role_paths(role, parent_role=parent_role)

        target_repositories = self._get_target_repositories()
        return [
            repo
            for repo in target_repositories
            if all([fnmatch(repo, path) for path in role_paths])
        ]

    def get_delegations_info(self, role_name):
        # load repository is not already loaded
        self._repository
        return tuf.roledb.get_roleinfo(role_name, self.name).get("delegations")

    def get_role_threshold(self, role, parent_role=None):
        """Get threshold of the given role

        Args:
        - role(str): TUF role (root, targets, timestamp, snapshot or delegated one)
        - parent_role(str): Name of the parent role of the delegated role. If not specified,
                            it will be set automatically, but this might be slow if there
                            are many delegations.

        Returns:
        Role's signatures threshold

        Raises:
        - securesystemslib.exceptions.FormatError: If the arguments are improperly formatted.
        - securesystemslib.exceptions.UnknownRoleError: If 'rolename' has not been delegated by this
        """
        role_obj = self._role_obj(role)
        if role_obj is None:
            return None
        try:
            return role_obj.threshold
        except KeyError:
            pass
        return self.get_delegated_role_property("threshold", role, parent_role)

    def get_signable_metadata(self, role):
        """Return signable portion of newly generate metadata for given role.

        Args:
        - role(str): TUF role (root, targets, timestamp, snapshot or delegated one)

        Returns:
        A string representing the 'object' encoded in canonical JSON form or None

        Raises:
        None
        """
        try:
            from tuf.keydb import get_key

            signable = None

            role_obj = self._role_obj(role)
            key = get_key(role_obj.keys[0])

            def _provider(key, data):
                nonlocal signable
                signable = securesystemslib.formats.encode_canonical(data)

            role_obj.add_external_signature_provider(key, _provider)
            self.writeall()
        except (IndexError, TUFError, SSLibError):
            return signable

    def _get_target_repositories(self):
        repositories_path = self.targets_path / "repositories.json"
        if repositories_path.exists():
            repositories = repositories_path.read_text()
            repositories = json.loads(repositories)["repositories"]
            return [str(Path(target_path).as_posix()) for target_path in repositories]

    def is_valid_metadata_key(self, role, key, scheme=DEFAULT_RSA_SIGNATURE_SCHEME):
        """Checks if metadata role contains key id of provided key.

        Args:
        - role(str): TUF role (root, targets, timestamp, snapshot or delegated one)
        - key(securesystemslib.formats.RSAKEY_SCHEMA): Role's key.

        Returns:
        Boolean. True if key id is in metadata role key ids, False otherwise.

        Raises:
        - securesystemslib.exceptions.FormatError: If key does not match RSAKEY_SCHEMA
        - securesystemslib.exceptions.UnknownRoleError: If role does not exist
        """

        if isinstance(key, str):
            key = import_rsakey_from_pem(key, scheme)

        securesystemslib.formats.RSAKEY_SCHEMA.check_match(key)

        return key["keyid"] in self.get_role_keys(role)

    def is_valid_metadata_yubikey(self, role, public_key=None):
        """Checks if metadata role contains key id from YubiKey.

        Args:
        - role(str): TUF role (root, targets, timestamp, snapshot or delegated one
        - public_key(securesystemslib.formats.RSAKEY_SCHEMA): RSA public key dict

        Returns:
        Boolean. True if smart card key id belongs to metadata role key ids

        Raises:
        - YubikeyError
        - securesystemslib.exceptions.FormatError: If 'PEM' is improperly formatted.
        - securesystemslib.exceptions.UnknownRoleError: If role does not exist
        """
        securesystemslib.formats.ROLENAME_SCHEMA.check_match(role)

        if public_key is None:
            public_key = yk.get_piv_public_key_tuf()

        return self.is_valid_metadata_key(role, public_key)

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

        def _map_targets_to_roles(role_name, target_filenames):
            roles_targets = {}
            delegations = self.get_delegations_info(role_name)
            if len(delegations):
                for role_info in delegations.get("roles"):
                    # check if this role can sign target_path
                    delegated_role_name = role_info["name"]
                    for path_pattern in role_info["paths"]:
                        for target_filename in target_filenames:
                            if fnmatch(
                                target_filename.lstrip(os.sep),
                                path_pattern.lstrip(os.sep),
                            ):
                                roles_targets[target_filename] = delegated_role_name
                    roles_targets.update(
                        _map_targets_to_roles(delegated_role_name, target_filenames)
                    )
            return roles_targets

        roles_targets = {
            target_filename: "targets" for target_filename in target_filenames
        }
        roles_targets.update(_map_targets_to_roles("targets", target_filenames))
        return roles_targets

    def remove_metadata_key(self, role, key_id):
        """Remove metadata key of the provided role.

        Args:
        - role(str): TUF role (root, targets, timestamp, snapshot or delegated one)
        - key_id(str): An object conformant to 'securesystemslib.formats.KEYID_SCHEMA'.

        Returns:
        None

        Raises:
        - securesystemslib.exceptions.FormatError: If the arguments are improperly formatted.
        - securesystemslib.exceptions.UnknownRoleError: If 'rolename' has not been delegated by this
                                                        targets object.
        - securesystemslib.exceptions.UnknownKeyError: If 'key_id' is not found in the keydb database.

        """
        from tuf.keydb import get_key

        key = get_key(key_id)
        self._role_obj(role).remove_verification_key(key)

    def roles_keystore_update_method(self, role_name):
        return {
            "timestamp": self.update_timestamp_keystores,
            "snapshot": self.update_snapshot_keystores,
            "targets": self.update_targets_keystores,
        }.get(role_name, self.update_targets_keystores)

    def roles_yubikeys_update_method(self, role_name):
        return {
            "timestamp": self.update_timestamp_yubikeys,
            "snapshot": self.update_snapshot_yubikeys,
            "targets": self.update_targets_yubikeys,
        }.get(role_name, self.update_targets_yubikeys)

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
        role_obj = self._role_obj(role)
        if start_date is None:
            start_date = datetime.datetime.now()
        if interval is None:
            try:
                interval = expiration_intervals[role]
            except KeyError:
                interval = expiration_intervals["targets"]

        expiration_date = start_date + datetime.timedelta(interval)
        role_obj.expiration = expiration_date

    def set_delegated_role_property(self, property_name, role, value, parent_role=None):
        """
        Set property of a delegated role by modifying its parent's "delegations" property
        Args:
            - property_name: Name of the property (like threshold)
            - role_name: Role
            - value: New value of the property
            - parent_role: Parent role
        """
        if parent_role is None:
            parent_role = self.find_delegated_roles_parent(role)

        roleinfo = tuf.roledb.get_roleinfo(parent_role, self.name)
        delegated_roles_info = roleinfo["delegations"]["roles"]
        for delegated_role_info in delegated_roles_info:
            if delegated_role_info["name"] == role:
                delegated_role_info[property_name] = value
                tuf.roledb.update_roleinfo(
                    parent_role, roleinfo, repository_name=self.name
                )
                break

    def sort_roles_targets_for_filenames(self):
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

    def update_root(self, signature_dict):
        """Update root metadata.

        Args:
        - signature_dict(dict): key_id-signature dictionary

        Returns:
        None

        Raises:
        - InvalidKeyError: If wrong key is used to sign metadata
        - SnapshotMetadataUpdateError: If any other error happened during metadata update
        """
        from tuf.keydb import get_key

        try:
            for key_id in signature_dict:
                key = get_key(key_id)
                self._repository.root.add_external_signature_provider(
                    key, partial(root_signature_provider, signature_dict, key_id)
                )
            self.writeall()
        except (TUFError, SSLibError) as e:
            raise RootMetadataUpdateError(str(e))

    def sign_role_keystores(self, role_name, signing_keys, write=True):
        """Load signing keys of the specified role and sign the metadata file
        if write is True. Should be used when the keys are not stored on Yubikeys.
        Args:
        - role_name(str): Name of the role which is to be updated
        - signing_keys(list[securesystemslib.formats.RSAKEY_SCHEMA]): A list of signing keys
        - write(bool): If True timestmap metadata will be signed and written

        Returns:
        None

        Raises:
        - InvalidKeyError: If at least one of the provided keys cannot be used to sign the
                          role's metadata
        - SigningError: If the number of signing keys is insufficient
        """
        threshold = self.get_role_threshold(role_name)
        if len(signing_keys) < threshold:
            raise SigningError(
                role_name,
                f"Insufficient number of signing keys. Signing threshold is {threshold}.",
            )
        for key in signing_keys:
            self._try_load_metadata_key(role_name, key)
        if write:
            self._repository.write(role_name)

    def sign_role_yubikeys(
        self,
        role_name,
        public_keys,
        signature_provider=yubikey_signature_provider,
        write=True,
        pins=None,
    ):
        """Register signature providers of the specified role and sign the metadata file
        if write is True.

        Args:
        - role_name(str): Name of the role which is to be updated
        - public_keys(list[securesystemslib.formats.RSAKEY_SCHEMA]): A list of public keys
        - signature_provider: Signature provider used for signing
        - write(bool): If True timestmap metadata will be signed and written
        - pins(dict): A dictionary mapping serial numbers of Yubikeys to their pins. If not
                      provided, pins will either be loaded from the global pins dictionary
                      (if it was previously populated) or the user will have to manually enter
                      it.
        Returns:
        None

        Raises:
        - InvalidKeyError: If at least one of the provided keys cannot be used to sign the
                          role's metadata
        - SigningError: If the number of signing keys is insufficient
        """
        role_obj = self._role_obj(role_name)
        threshold = self.get_role_threshold(role_name)
        if len(public_keys) < threshold:
            raise SigningError(
                role_name,
                f"Insufficient number of signing keys. Signing threshold is {threshold}.",
            )

        if pins is not None:
            for serial_num, pin in pins.items():
                yk.add_key_pin(serial_num, pin)

        for index, public_key in enumerate(public_keys):
            if public_key is None:
                public_key = yk.get_piv_public_key_tuf()

            if not self.is_valid_metadata_yubikey(role_name, public_key):
                raise InvalidKeyError(role_name)

            if len(public_keys) == 1:
                key_name = role_name
            else:
                key_name = f"{role_name}{index + 1}"

            role_obj.add_external_signature_provider(
                public_key, partial(signature_provider, key_name, public_key["keyid"])
            )

        if write:
            self._repository.write(role_name)

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

    def unmark_dirty_role(self, role):
        """
        Unmakes one dirty role. This means that the corresponding metadata file
        will not be updated.
        Args:
        - role which should be unmaked
        """
        self.unmark_dirty_roles([role])

    def unmark_dirty_roles(self, roles):
        """
        Unmakes dirty roles. This means that the corresponding metadata files
        will not be updated.
        Args:
        - roles which should be unmaked
        """
        self._repository.unmark_dirty(roles)

    def update_role_keystores(
        self, role_name, signing_keys, start_date=None, interval=None, write=True
    ):
        """Update the specified role's metadata's expiration date by setting it to a date calculated by
        adding the specified interval to start date. Load the signing keys and sign the file if
        write is set to True.
        Should be used when the keys are not stored on Yubikeys.

        Args:
        - role_name: Name of the role whose metadata is to be updated
        - signing_keys: list of signing keys of the specified role
        - start_date(datetime): Date to which the specified interval is added when
                                calculating expiration date. If no value is provided,
                                it is set to the current time
        - interval(int): Number of days added to the start date. If not provided,
                         the default expiration interval of the specified role is used
        - write(bool): If True metadata will be signed and written

        Returns:
        None

        Raises:
        - InvalidKeyError: If a wrong key is used to sign metadata
        - MetadataUpdateError: If any other error happened while updating and signing
                               the metadata file
        """
        try:
            self.set_metadata_expiration_date(role_name, start_date, interval)
            self.sign_role_keystores(role_name, signing_keys, write)
        except (YubikeyError, TUFError, SSLibError, SigningError) as e:
            raise MetadataUpdateError(role_name, str(e))

    def update_role_yubikeys(
        self,
        role_name,
        public_keys,
        start_date=None,
        interval=None,
        write=True,
        signature_provider=yubikey_signature_provider,
        pins=None,
    ):
        """Update the specified role's metadata expiration date by setting it to a date calculated by
        adding the specified interval to start date. Register Yubikey signature providers and
        sign the metadata file if write is set to True.

        Args:
        - role_name: Name of the role whose metadata is to be updated
        - public_keys: list of public keys of the specified role
        - start_date(datetime): Date to which the specified interval is added when
                                calculating expiration date. If no value is provided,
                                it is set to the current time
        - interval(int): Number of days added to the start date. If not provided,
                         the default expiration interval of the specified role is used
        - write(bool): If True timestamp metadata will be signed and written
        - signature_provider: Signature provider used for signing
        - pins(dict): A dictionary mapping serial numbers of Yubikeys to their pins. If not
                      provided, pins will either be loaded from the global pins dictionary
                      (if it was previously populated) or the user will have to manually enter
                      it.
        Returns:
        None

        Raises:
        - InvalidKeyError: If a wrong key is used to sign metadata
        - MetadataUpdateError: If any other error happened while updating and signing
                               the metadata file
        """
        try:
            self.set_metadata_expiration_date(role_name, start_date, interval)
            self.sign_role_yubikeys(
                role_name,
                public_keys,
                signature_provider=signature_provider,
                write=write,
                pins=pins,
            )
        except (YubikeyError, TUFError, SSLibError, SigningError) as e:
            raise MetadataUpdateError(role_name, str(e))

    def update_timestamp_keystores(
        self, timestamp_signing_keys, start_date=None, interval=None, write=True
    ):
        """Update timestamp metadata's expiration date by setting it to a date calculated by
        adding the specified interval to start date. Load the signing keys and sign the file if
        write is set to True.
        Should be used when the keys are not stored on Yubikeys.

        Args:
        - timestamp_signing_keys: list of signing keys of the timestamp role
        - start_date(datetime): Date to which the specified interval is added when
                                calculating expiration date. If no value is provided,
                                it is set to the current time
        - interval(int): Number of days added to the start date. If not provided,
                         the default timestamp expiration interval is used (1 day)
        - write(bool): If True timestamp metadata will be signed and written

        Returns:
        None

        Raises:
        - InvalidKeyError: If a wrong key is used to sign metadata
        - TimestampMetadataUpdateError: If any other error happened while updating and signing
                                        the metadata file
        """
        try:
            self.update_role_keystores(
                "timestamp", timestamp_signing_keys, start_date, interval, write
            )
        except MetadataUpdateError as e:
            raise TimestampMetadataUpdateError(str(e))

    def update_timestamp_yubikeys(
        self,
        timestamp_public_keys,
        start_date=None,
        interval=None,
        write=True,
        pins=None,
    ):
        """Update timestamp metadata's expiration date by setting it to a date calculated by
        adding the specified interval to start date. Register Yubikey signature providers and
        sign the metadata file if write is set to True.

        Args:
        - timestamp_public_keys: list of public keys of the timestamp role
        - start_date(datetime): Date to which the specified interval is added when
                                calculating expiration date. If no value is provided,
                                it is set to the current time
        - interval(int): Number of days added to the start date. If not provided,
                         the default timestamp expiration interval is used (1 day)
        - write(bool): If True timestamp metadata will be signed and written
        - pins(dict): A dictionary mapping serial numbers of Yubikeys to their pins. If not
                      provided, pins will either be loaded from the global pins dictionary
                      (if it was previously populated) or the user will have to manually enter
                      it.

        Returns:
        None

        Raises:
        - InvalidKeyError: If a wrong key is used to sign metadata
        - TimestampMetadataUpdateError: If any other error happened while updating and signing
                                        the metadata file
        """
        try:
            self.update_role_yubikeys(
                "timestamp",
                timestamp_public_keys,
                start_date,
                interval,
                write=write,
                pins=pins,
            )
        except MetadataUpdateError as e:
            raise TimestampMetadataUpdateError(str(e))

    def update_snapshot_keystores(
        self, snapshot_signing_keys, start_date=None, interval=None, write=True
    ):
        """Update snapshot metadata's expiration date by setting it to a date calculated by
        adding the specified interval to start date. Load the signing keys and sign the file if
        write is set to True.
        Should be used when the keys are not stored on Yubikeys.

        Args:
        - snapshot_signing_keys: list of signing keys of the snapshot role
        - start_date(datetime): Date to which the specified interval is added when
                                calculating expiration date. If no value is provided,
                                it is set to the current time
        - interval(int): Number of days added to the start date. If not provided,
                         the default snapshot expiration interval is used (7 days)
        - write(bool): If True snapshot metadata will be signed and written

        Returns:
        None

        Raises:
        - InvalidKeyError: If a wrong key is used to sign metadata
        - SnapshotMetadataUpdateError: If any other error happened while updating and signing
                                       the metadata file
        """
        try:
            self.update_role_keystores(
                "snapshot", snapshot_signing_keys, start_date, interval, write
            )
        except MetadataUpdateError as e:
            raise SnapshotMetadataUpdateError(str(e))

    def update_snapshot_yubikeys(
        self,
        snapshot_public_keys,
        start_date=None,
        interval=None,
        write=True,
        pins=None,
    ):
        """Update snapshot metadata's expiration date by setting it to a date calculated by
        adding the specified interval to start date. Register Yubikey signature providers and
        sign the metadata file if write is set to True

        Args:
        - snapshot_public_keys: list of public keys of the snapshot role
        - start_date(datetime): Date to which the specified interval is added when
                                calculating expiration date. If no value is provided,
                                it is set to the current time
        - interval(int): Number of days added to the start date. If not provided,
                         the default snapshot expiration interval is used (7 days)
        - write(bool): If True snapshot metadata will be signed and written
        - pins(dict): A dictionary mapping serial numbers of Yubikeys to their pins. If not
                      provided, pins will either be loaded from the global pins dictionary
                      (if it was previously populated) or the user will have to manually enter
                      it.

        Returns:
        None

        Raises:
        - InvalidKeyError: If a wrong key is used to sign metadata
        - SnapshotMetadataUpdateError: If any other error happened while updating and signing
                                       the metadata file
        """
        try:
            self.update_role_yubikeys(
                "snapshot",
                snapshot_public_keys,
                start_date,
                interval,
                write=write,
                pins=pins,
            )
        except MetadataUpdateError as e:
            raise SnapshotMetadataUpdateError(str(e))

    def update_targets_keystores(
        self,
        targets_signing_keys,
        added_targets_data=None,
        removed_targets_data=None,
        start_date=None,
        interval=None,
        write=True,
    ):
        """Update a targets role's metadata. The role can be either be main targets role or a delegated
        one. If targets_data is specified, updates metadata corresponding to target files contained
        if that dictionary. Set the new expiration date by to a value calculated by adding the
        specified interval to start date. Load the signing keys and sign the file if write is set to True.
        Should be used when the keys are not stored on Yubikeys.

        Args:
        - targets_signing_keys: list of signing keys of the targets role
        - start_date(datetime): Date to which the specified interval is added when
                                calculating expiration date. If no value is provided,
                                it is set to the current time
        - added_targets_data(dict): Dictionary containing targets data that should be added
        - removed_targets_data(dict): Dictionary containing targets data that should be removed
        - interval(int): Number of days added to the start date. If not provided,
                         the default targets expiration interval is used (90 days)
        - write(bool): If True targets metadata will be signed and written

        Returns:
        None

        Raises:
        - TargetsMetadataUpdateError: If any other error happened while updating and signing
                                      the metadata file
        """
        try:
            targets_role = self.modify_targets(added_targets_data, removed_targets_data)
            self.update_role_keystores(
                targets_role, targets_signing_keys, start_date, interval, write
            )
        except Exception as e:
            raise TargetsMetadataUpdateError(str(e))

    def update_targets_yubikeys(
        self,
        targets_public_keys,
        added_targets_data=None,
        removed_targets_data=None,
        start_date=None,
        interval=None,
        write=True,
        pins=None,
    ):
        """Update a targets role's metadata. The role can be either be main targets role or a delegated
        one. If targets_data is specified, updates metadata corresponding to target files contained
        if that dictionary. Set the new expiration date by to a value calculated by adding the
        specified interval to start date. Register Yubikey signature providers and
        sign the metadata file if write is set to True.

        Args:
        - targets_public_keys: list of signing keys of the targets role
        - start_date(datetime): Date to which the specified interval is added when
                                calculating expiration date. If no value is provided,
                                it is set to the current time
        - added_targets_data(dict): Dictionary containing targets data that should be added
        - removed_targets_data(dict): Dictionary containing targets data that should be removed
        - interval(int): Number of days added to the start date. If not provided,
                         the default targets expiration interval is used (90 days in case of
                         "targets", 1 in case of delegated roles)
        - write(bool): If True targets metadata will be signed and written
        - pins(dict): A dictionary mapping serial numbers of Yubikeys to their pins. If not
                      provided, pins will either be loaded from the global pins dictionary
                      (if it was previously populated) or the user will have to manually enter
                      it.
        Returns:
        None

        Raises:
        - TargetsMetadataUpdateError: If error happened while updating and signing
                                      the metadata file
        """
        try:
            targets_role = self.modify_targets(added_targets_data, removed_targets_data)
            self.update_role_yubikeys(
                targets_role,
                targets_public_keys,
                start_date,
                interval,
                write=write,
                pins=pins,
            )
        except Exception as e:
            raise TargetsMetadataUpdateError(str(e))

    def writeall(self):
        """Write all dirty metadata files.

        Args:
        None

        Returns:
        None

        Raises:
        - tuf.exceptions.UnsignedMetadataError: If any of the top-level and delegated roles do not
                                                have the minimum threshold of signatures.
        """
        self._repository.writeall()
