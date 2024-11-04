import datetime
import json
import operator
import os
import shutil
from cryptography.hazmat.primitives import serialization
from fnmatch import fnmatch
from functools import partial, reduce
from pathlib import Path
from typing import Dict

import securesystemslib
import tuf.roledb
from securesystemslib.exceptions import Error as SSLibError
from securesystemslib.interface import import_rsa_privatekey_from_file
from tuf.exceptions import Error as TUFError, RepositoryError
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
    KeystoreError,
)
from taf.git import GitRepository
from taf.utils import (
    default_backend,
    normalize_file_line_endings,
    on_rm_error,
    get_file_details,
)
from taf import YubikeyMissingLibrary
try:
    import taf.yubikey as yk
except ImportError:
    yk = YubikeyMissingLibrary()  # type: ignore


# Default expiration intervals per role
expiration_intervals = {"root": 365, "targets": 90, "snapshot": 7, "timestamp": 1}

# Loaded keys cache
role_keys_cache: Dict = {}



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
        try:
            if password is not None:
                key = import_rsa_privatekey_from_file(
                    str(Path(keystore, role)), password, scheme=scheme
                )
            else:
                key = import_rsa_privatekey_from_file(
                    str(Path(keystore, role)), scheme=scheme
                )
        except FileNotFoundError:
            raise KeystoreError(f"Cannot find {role} key in {keystore}")
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
        input(f"\nInsert {name} and press enter")

    signature = yk.sign_piv_rsa_pkcs1v15(data, pin)
    return {"keyid": key_id, "sig": hexlify(signature).decode()}


class Repository:
    def __init__(self, path, name="default"):
        self.path = Path(path)
        self.name = name

    _framework_files = ["repositories.json", "test-auth-repo"]


    _tuf_repository = None

    @property
    def _repository(self):
        if self._tuf_repository is None:
            self._load_tuf_repository(self.path)
        return self._tuf_repository

    @property
    def repo_id(self):
        return GitRepository(path=self.path).initial_commit

    @property
    def certs_dir(self):
        certs_dir = self.path / "certs"
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
        targets_directory_length = len(targets_obj._targets_directory) + 1
        relative_path = file_path[targets_directory_length:].replace("\\", "/")
        normalize_file_line_endings(file_path)

        targets_obj.add_target(relative_path, custom)

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
        # before attempting to load tuf repository, create empty targets directory if it does not
        # exist to avoid errors raised by tuf
        targets_existed = True
        if not self.targets_path.is_dir():
            targets_existed = False
            self.targets_path.mkdir(parents=True, exist_ok=True)
        current_dir = self.metadata_path / "current"
        previous_dir = self.metadata_path / "previous"
        if current_dir.is_dir():
            shutil.rmtree(current_dir)
        if previous_dir.is_dir():
            shutil.rmtree(previous_dir)
        try:
            self._tuf_repository = load_repository(str(path), self.name)
        except RepositoryError:
            if not targets_existed:
                self.targets_path.rmdir()
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
        try:
            return self._repository.targets(role)
        except tuf.exceptions.UnknownRoleError:
            return

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




    def get_key_length_and_scheme_from_metadata(self, parent_role, keyid):
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
            return pub_key, scheme
        except Exception:
            return None, None

    def generate_roles_description(self) -> Dict:
        roles_description = {}

        def _get_delegations(role_name):
            delegations_info = {}
            delegations = self.get_delegations_info(role_name)
            if len(delegations):
                for role_info in delegations.get("roles"):
                    delegations_info[role_info["name"]] = {
                        "threshold": role_info["threshold"],
                        "number": len(role_info["keyids"]),
                        "paths": role_info["paths"],
                        "terminating": role_info["terminating"],
                    }
                    pub_key, scheme = self.get_key_length_and_scheme_from_metadata(
                        role_name, role_info["keyids"][0]
                    )
                    delegations_info[role_info["name"]]["scheme"] = scheme
                    delegations_info[role_info["name"]]["length"] = pub_key.key_size
                    inner_roles_data = _get_delegations(role_info["name"])
                    if len(inner_roles_data):
                        delegations_info[role_info["name"]][
                            "delegations"
                        ] = inner_roles_data
            return delegations_info

        for role_name in MAIN_ROLES:
            role_obj = self._role_obj(role_name)
            roles_description[role_name] = {
                "threshold": role_obj.threshold,
                "number": len(role_obj.keys),
            }
            pub_key, scheme = self.get_key_length_and_scheme_from_metadata(
                "root", role_obj.keys[0]
            )
            roles_description[role_name]["scheme"] = scheme
            roles_description[role_name]["length"] = pub_key.key_size
            if role_name == "targets":
                delegations_info = _get_delegations(role_name)
                if len(delegations_info):
                    roles_description[role_name]["delegations"] = delegations_info
        return {"roles": roles_description}



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
            if any([fnmatch(repo, path) for path in role_paths])
        ]

    def get_delegations_info(self, role_name):
        # load repository is not already loaded
        self._repository
        return tuf.roledb.get_roleinfo(role_name, self.name).get("delegations")


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
        securesystemslib.formats.NAME_SCHEMA.check_match(role)

        if public_key is None:
            public_key = yk.get_piv_public_key_tuf()

        return self.is_valid_metadata_key(role, public_key)


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


def _tuf_patches():
    from functools import wraps
    import tuf.repository_lib
    import tuf.repository_tool

    from taf.utils import normalize_file_line_endings

    # Replace staging metadata directory name
    tuf.repository_tool.METADATA_STAGED_DIRECTORY_NAME = (
        tuf.repository_tool.METADATA_DIRECTORY_NAME
    )

    # Replace get_metadata_fileinfo with file-endings normalization
    def get_targets_metadata_fileinfo(get_targets_metadata_fileinfo_fn):
        @wraps(get_targets_metadata_fileinfo_fn)
        def normalized(filename, storage_backend, custom=None):
            normalize_file_line_endings(filename)
            return get_targets_metadata_fileinfo_fn(
                filename, storage_backend, custom=None
            )

        return normalized

    tuf.repository_lib.get_targets_metadata_fileinfo = get_targets_metadata_fileinfo(
        tuf.repository_lib.get_targets_metadata_fileinfo
    )


_tuf_patches()
