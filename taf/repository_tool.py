import datetime
import json
from functools import partial
from pathlib import Path

import securesystemslib
import tuf.repository_tool
from securesystemslib.exceptions import Error as SSLibError
from securesystemslib.interface import import_rsa_privatekey_from_file
from taf.constants import DEFAULT_RSA_SIGNATURE_SCHEME
from taf.exceptions import (
    InvalidKeyError,
    MetadataUpdateError,
    RootMetadataUpdateError,
    SnapshotMetadataUpdateError,
    TargetsMetadataUpdateError,
    TimestampMetadataUpdateError,
    YubikeyError,
    SigningError,
)
from taf.git import GitRepository
from taf.utils import normalize_file_line_endings
from tuf.exceptions import Error as TUFError
from tuf.repository_tool import (
    METADATA_DIRECTORY_NAME,
    TARGETS_DIRECTORY_NAME,
    import_rsakey_from_pem,
    load_repository,
)

# Default expiration intervals per role
expiration_intervals = {"root": 365, "targets": 90, "snapshot": 7, "timestamp": 1}

# Loaded keys cache
role_keys_cache = {}


DISABLE_KEYS_CACHING = False


def get_delegated_role_property(property_name, role_name, parent_role=None):
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
        parent_role = find_delegated_roles_parent(role_name)
    parents_role_info = tuf.roledb.get_roleinfo(parent_role)
    delegations = parents_role_info.get("delegations")
    for delegated_role in delegations["roles"]:
        if delegated_role["name"] == role_name:
            return delegated_role[property_name]
    return None


def find_delegated_roles_parent(role_name):
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
        targets_role_info = tuf.roledb.get_roleinfo(parent_role_name)
        delegations = targets_role_info.get("delegations")
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
    import taf.yubikey as yk
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
    def __init__(self, repository_path):
        self.repository_path = repository_path
        tuf.repository_tool.METADATA_STAGED_DIRECTORY_NAME = METADATA_DIRECTORY_NAME
        tuf_repository = load_repository(repository_path)
        self._repository = tuf_repository

    _framework_files = ["repositories.json", "test-auth-repo"]

    @property
    def targets_path(self):
        return Path(self.repository_path, TARGETS_DIRECTORY_NAME)

    @property
    def metadata_path(self):
        return Path(self.repository_path, METADATA_DIRECTORY_NAME)

    @property
    def repo_id(self):
        return GitRepository(self.repository_path).initial_commit

    @property
    def certs_dir(self):
        certs_dir = Path(self.repository_path, "certs")
        certs_dir.mkdir(parents=True, exist_ok=True)
        return str(certs_dir)

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
        normalize_file_line_endings(file_path)
        targets_obj.add_target(file_path, custom)

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

    def add_targets(self, data, targets_role="targets", files_to_keep=None):
        """Creates a target.json file containing a repository's commit for each repository.
        Adds those files to the tuf repository. Also removes all targets from the filesystem if their
        path is not among the provided ones. TUF does not delete targets automatically.

        Args:
        - data(dict): Dictionary whose keys are target paths of repositories
                        (as specified in targets.json, relative to the targets dictionary).
                        The values are of form:
                        {
                        target: content of the target file
                        custom: {
                            custom_field1: custom_value1,
                            custom_field2: custom_value2
                        }
                        }

        Content of the target file can be a dictionary, in which case a jason file will be created.
        If that is not the case, an ordinary textual file will be created.
        If content is not specified and the file already exists, it will not be modified.
        If it does not exist, an empty file will be created. To replace an existing file with an
        empty file, specify empty content (target: '')

        If a target exists on disk, but is not specified in the provided targets data dictionary,
        it will be:
        - removed, if the target does not correspond to a repository defined in repositories.json
        - left as is,  if the target does correspondw to a repository defined in repositories.json

        Custom is an optional property which, if present, will be used to specify a TUF target's

        - targets_role(str): Targets or delegated role: a targets role (the root targets role
                            or one of the delegated ones)
        - files_to_keep(list|tuple): List of files defined in the previous version of targets.json
                                    that should remain targets. Files required by the framework will
                                    also remain targets.
        """
        if files_to_keep is None:
            files_to_keep = []
        # leave all files required by the framework and additional files specified by the user
        files_to_keep.extend(self._framework_files)
        # add all repositories defined in repositories.json to files_to_keep
        files_to_keep.extend(self._get_target_repositories())
        # delete files if they no longer correspond to a target defined
        # in targets metadata and are not specified in files_to_keep
        targets_obj = self._role_obj(targets_role)
        for filepath in self.targets_path.rglob("*"):
            if filepath.is_file():
                file_rel_path = str(
                    Path(filepath).relative_to(self.targets_path).as_posix()
                )
                if file_rel_path not in data and file_rel_path not in files_to_keep:
                    if file_rel_path in targets_obj.target_files:
                        targets_obj.remove_target(file_rel_path)
                    filepath.unlink()

        for path, target_data in data.items():
            # if the target's parent directory should not be "targets", create
            # its parent directories if they do not exist
            target_path = (self.targets_path / path).absolute()
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

            custom = target_data.get("custom", None)
            self._add_target(targets_obj, str(target_path), custom)

        previous_targets = json.loads(
            Path(self.metadata_path, f"{targets_role}.json").read_text()
        )["signed"]["targets"]

        for path in files_to_keep:
            # if path if both in data and files_to_keep, skip it
            # e.g. repositories.json will always be in files_to_keep,
            # but it might also be specified in data, if it needs to be updated
            if path in data:
                continue
            target_path = (self.targets_path / path).absolute()
            previous_custom = None
            if path in previous_targets:
                previous_custom = previous_targets[path].get("custom")
            if target_path.is_file():
                self._add_target(targets_obj, str(target_path), previous_custom)

    def delete_unregistered_target_files(self, targets_role="targets"):
        """
        Delete all target files not specified in targets.json
        """
        targets_obj = self._role_obj(targets_role)
        for filepath in self.targets_path.rglob("*"):
            if filepath.is_file():
                file_rel_path = str(
                    Path(filepath).relative_to(self.targets_path).as_posix()
                )
                if file_rel_path not in targets_obj.target_files:
                    filepath.unlink()

    def _get_target_repositories(self):
        repositories_path = self.targets_path / "repositories.json"
        if repositories_path.exists():
            repositories = repositories_path.read_text()
            repositories = json.loads(repositories)["repositories"]
            return [str(Path(target_path).as_posix()) for target_path in repositories]

    def get_role_keys(self, role, parent_role=None):
        """Registers new target files with TUF.
        The files are expected to be inside the targets directory.

        Args:
        - role(str): TUF role (root, targets, timestamp, snapshot or delegated one)

        Returns:
        List of the role's keyids (i.e., keyids of the keys).

        Raises:
        - securesystemslib.exceptions.FormatError: If the arguments are improperly formatted.
        - securesystemslib.exceptions.UnknownRoleError: If 'rolename' has not been delegated by this
                                                        targets object.
        """
        role_obj = self._role_obj(role)
        try:
            return role_obj.keys
        except KeyError:
            pass
        return get_delegated_role_property("keyids", role, parent_role)

    def get_role_threshold(self, role, parent_role=None):
        try:
            return self._role_obj(role).threshold
        except KeyError:
            pass
        return get_delegated_role_property("threshold", role, parent_role)

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

    def is_valid_metadata_key(self, role, key):
        """Checks if metadata role contains key id of provided key.

        Args:
        - role(str): TUF role (root, targets, timestamp, snapshot or delegated one)
        - key(securesystemslib.formats.RSAKEY_SCHEMA): Timestamp key.

        Returns:
        Boolean. True if key id is in metadata role key ids, False otherwise.

        Raises:
        - securesystemslib.exceptions.FormatError: If key does not match RSAKEY_SCHEMA
        - securesystemslib.exceptions.UnknownRoleError: If role does not exist
        """
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
            from taf.yubikey import get_piv_public_key_tuf

            public_key = get_piv_public_key_tuf()

        return self.is_valid_metadata_key(role, public_key)

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

        key = import_rsakey_from_pem(pub_key_pem, scheme)
        self._role_obj(role).add_verification_key(key)

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
        }.get(role_name, partial(self.update_targets_keystores, targets_role=role_name))

    def roles_yubikeys_update_method(self, role_name):
        return {
            "timestamp": self.update_timestamp_yubikeys,
            "snapshot": self.update_snapshot_yubikeys,
            "targets": self.update_targets_yubikeys,
        }.get(role_name, partial(self.update_targets_yubikeys, targets_role=role_name))

    def set_metadata_expiration_date(
        self, role, start_date=datetime.datetime.now(), interval=None
    ):
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
                            all other roles - 1 day

        Returns:
        None

        Raises:
        - securesystemslib.exceptions.FormatError: If the arguments are improperly formatted.
        - securesystemslib.exceptions.UnknownRoleError: If 'rolename' has not been delegated by this
                                                        targets object.
        """
        role_obj = self._role_obj(role)
        if interval is None:
            interval = expiration_intervals.get(role, 1)
        expiration_date = start_date + datetime.timedelta(interval)
        role_obj.expiration = expiration_date

    def get_expiration_date(self, role):
        return self._role_obj(role).expiration

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
    ):
        """Register signature providers of the specified role and sign the metadata file
        if write is True.

        Args:
        - role_name(str): Name of the role which is to be updated
        - public_keys(list[securesystemslib.formats.RSAKEY_SCHEMA]): A list of public keys
        - signature_provider: Signature provider used for signing
        - write(bool): If True timestmap metadata will be signed and written

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
        for index, public_key in enumerate(public_keys):
            if public_key is None:
                from taf.yubikey import get_piv_public_key_tuf

                public_key = get_piv_public_key_tuf()

            if not self.is_valid_metadata_yubikey(role_name, public_key):
                raise InvalidKeyError(role_name)

            key_name = f"{role_name}{index + 1}"

            role_obj.add_external_signature_provider(
                public_key, partial(signature_provider, key_name, public_key["keyid"])
            )

        if write:
            self._repository.write(role_name)

    def _update_role_keystores(
        self,
        role_name,
        signing_keys,
        start_date=datetime.datetime.now(),
        interval=None,
        write=True,
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
            self.sign_role_keystores(role_name, signing_keys)
        except (YubikeyError, TUFError, SSLibError, SigningError) as e:
            raise MetadataUpdateError(role_name, str(e))

    def _update_role_yubikeys(
        self,
        role_name,
        public_keys,
        start_date=datetime.datetime.now(),
        interval=None,
        write=True,
        signature_provider=yubikey_signature_provider,
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

        Returns:
        None

        Raises:
        - InvalidKeyError: If a wrong key is used to sign metadata
        - MetadataUpdateError: If any other error happened while updating and signing
                               the metadata file
        """
        try:
            self.set_metadata_expiration_date(role_name, start_date, interval)
            self.sign_role_yubikeys(role_name, public_keys)
        except (YubikeyError, TUFError, SSLibError, SigningError) as e:
            raise MetadataUpdateError(role_name, str(e))

    def update_timestamp_keystores(
        self,
        timestamp_signing_keys,
        start_date=datetime.datetime.now(),
        interval=None,
        write=True,
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
            self._update_role_keystores(
                "timestamp", timestamp_signing_keys, start_date, interval, write
            )
        except MetadataUpdateError as e:
            raise TimestampMetadataUpdateError(e.message)

    def update_timestamp_yubikeys(
        self,
        timestamp_public_keys,
        start_date=datetime.datetime.now(),
        interval=None,
        write=True,
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

        Returns:
        None

        Raises:
        - InvalidKeyError: If a wrong key is used to sign metadata
        - TimestampMetadataUpdateError: If any other error happened while updating and signing
                                        the metadata file
        """
        try:
            self._update_role_yubikeys(
                "timestamp", timestamp_public_keys, start_date, interval, write
            )
        except MetadataUpdateError as e:
            raise TimestampMetadataUpdateError(e.message)

    def update_snapshot_keystores(
        self,
        snapshot_signing_keys,
        start_date=datetime.datetime.now(),
        interval=None,
        write=True,
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
            self._update_role_keystores(
                "snapshot", snapshot_signing_keys, start_date, interval, write
            )
        except MetadataUpdateError as e:
            raise SnapshotMetadataUpdateError(e.message)

    def update_snapshot_yubikeys(
        self,
        snapshot_public_keys,
        start_date=datetime.datetime.now(),
        interval=None,
        write=True,
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

        Returns:
        None

        Raises:
        - InvalidKeyError: If a wrong key is used to sign metadata
        - SnapshotMetadataUpdateError: If any other error happened while updating and signing
                                       the metadata file
        """
        try:
            self._update_role_yubikeys(
                "snapshot", snapshot_public_keys, start_date, interval, write
            )
        except MetadataUpdateError as e:
            raise SnapshotMetadataUpdateError(e.message)

    def update_targets_keystores(
        self,
        targets_signing_keys,
        targets_data=None,
        start_date=datetime.datetime.now(),
        interval=None,
        write=True,
        targets_role="targets",
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
        - targets_data(dict): (Optional) Dictionary containing targets data
        - interval(int): Number of days added to the start date. If not provided,
                         the default targets expiration interval is used (90 days)
        - write(bool): If True targets metadata will be signed and written
        - targets_role(str): Name of the targets role. Set to "targets" by default

        Returns:
        None

        Raises:
        - InvalidKeyError: If a wrong key is used to sign metadata
        - TargetsMetadataUpdateError: If any other error happened while updating and signing
                                      the metadata file
        """
        try:
            if targets_data:
                self.add_targets(targets_data)
            self._update_role_keystores(
                targets_role, targets_signing_keys, start_date, interval, write
            )
        except MetadataUpdateError as e:
            raise TargetsMetadataUpdateError(e.message)

    def update_targets_yubikeys(
        self,
        targets_public_keys,
        targets_data=None,
        start_date=datetime.datetime.now(),
        interval=None,
        write=True,
        targets_role="targets",
    ):
        """Update a targets role's metadata. The role can be either be main targets role or a delegated
        one. If targets_data is specified, updates metadata corresponding to target files contained
        if that dictionary. Set the new expiration date by to a value calculated by adding the
        specified interval to start date. Register Yubikey signature providers and
        sign the metadata file if write is set to True.

        Args:
        - targets_signing_keys: list of signing keys of the targets role
        - start_date(datetime): Date to which the specified interval is added when
                                calculating expiration date. If no value is provided,
                                it is set to the current time
        - targets_data(dict): (Optional) Dictionary containing targets data
        - interval(int): Number of days added to the start date. If not provided,
                         the default targets expiration interval is used (90 days in case of
                         "targets", 1 in case of delegated roles)
        - write(bool): If True targets metadata will be signed and written
        - targets_role(str): Name of the targets role. Set to "targets" by default

        Returns:
        None

        Raises:
        - InvalidKeyError: If a wrong key is used to sign metadata
        - TargetsMetadataUpdateError: If any other error happened while updating and signing
                                      the metadata file
        """
        try:
            if targets_data:
                self.add_targets(targets_data)
            self._update_role_yubikeys(
                targets_role, targets_public_keys, start_date, interval, write
            )
        except MetadataUpdateError as e:
            raise TargetsMetadataUpdateError(e.message)

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
