import datetime
import json
from functools import partial
from pathlib import Path

import securesystemslib
import tuf.repository_tool
from securesystemslib.exceptions import Error as SSLibError
from securesystemslib.interface import import_rsa_privatekey_from_file
from tuf.exceptions import Error as TUFError
from tuf.repository_tool import (
    METADATA_DIRECTORY_NAME,
    TARGETS_DIRECTORY_NAME,
    import_rsakey_from_pem,
    load_repository,
)

from taf.constants import DEFAULT_RSA_SIGNATURE_SCHEME
from taf.exceptions import (
    InvalidKeyError,
    MetadataUpdateError,
    RootMetadataUpdateError,
    SnapshotMetadataUpdateError,
    TargetsMetadataUpdateError,
    TimestampMetadataUpdateError,
    YubikeyError,
)
from taf.git import GitRepository
from taf.utils import normalize_file_line_endings

# Default expiration intervals per role
expiration_intervals = {"root": 365, "targets": 90, "snapshot": 7, "timestamp": 1}

# Loaded keys cache
role_keys_cache = {}


DISABLE_KEYS_CACHING = False


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


def targets_signature_provider(key_id, key_pin, key, data):  # pylint: disable=W0613
    """Targets signature provider used to sign data with YubiKey.

    Args:
        - key_id(str): Key id from targets metadata file
        - key_pin(str): PIN for signing key
        - key(securesystemslib.formats.RSAKEY_SCHEMA): Key info
        - data(dict): Data to sign

    Returns:
        Dictionary that comforms to `securesystemslib.formats.SIGNATURE_SCHEMA`

    Raises:
        - YubikeyError: If signing with YubiKey cannot be performed
    """
    from taf.yubikey import sign_piv_rsa_pkcs1v15
    from binascii import hexlify

    data = securesystemslib.formats.encode_canonical(data).encode("utf-8")
    signature = sign_piv_rsa_pkcs1v15(data, key_pin)

    return {"keyid": key_id, "sig": hexlify(signature).decode()}


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
            input(f"Insert {name} and press enter")
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
        pin = _check_key_and_get_pin(key_id)
        if pin is not None:
            break

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

    def _update_metadata(
        self, role, start_date=datetime.datetime.now(), interval=None, write=False
    ):
        """Update metadata expiration date and (optionally) writes it.

        Args:
        - role(str): TUF role (root, targets, timestamp, snapshot or delegated one)
        - start_date(datetime): Date to which the specified interval is added when
                                calculating expiration date. If a value is not
                                provided, it is set to the current time
        - interval(int): Number of days added to the start date. If not provided,
                        the default value is used
        - write(bool): If True metadata will be signed and written

        Returns:
        - None

        Raises:
        - securesystemslib.exceptions.Error: If securesystemslib error happened during metadata write
        - tuf.exceptions.Error: If TUF error happened during metadata write
        """
        self.set_metadata_expiration_date(role, start_date, interval)
        if write:
            self._repository.write(role)

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

    def _get_target_repositories(self):
        repositories_path = self.targets_path / "repositories.json"
        if repositories_path.exists():
            repositories = repositories_path.read_text()
            repositories = json.loads(repositories)["repositories"]
            return [str(Path(target_path).as_posix()) for target_path in repositories]

    def get_role_keys(self, role):
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
        return role_obj.keys

    def get_role_threshold(self, role):
        return self._role_obj(role).threshold

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

            def _provider(data):
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

    def update_snapshot(
        self,
        snapshot_key,
        start_date=datetime.datetime.now(),
        interval=None,
        write=True,
    ):
        """Update snapshot metadata.

        Args:
        - snapshot_key
        - password: Keystore file password
        - start_date(datetime): Date to which the specified interval is added when
                                calculating expiration date. If a value is not
                                provided, it is set to the current time
        - interval(int): Number of days added to the start date. If not provided,
                        the default value is used
        - write(bool): If True snapshot metadata will be signed and written

        Returns:
        None

        Raises:
        - InvalidKeyError: If wrong key is used to sign metadata
        - SnapshotMetadataUpdateError: If any other error happened during metadata update
        """
        try:
            self._try_load_metadata_key("snapshot", snapshot_key)
            self._update_metadata("snapshot", start_date, interval, write=write)
        except (TUFError, SSLibError) as e:
            raise SnapshotMetadataUpdateError(str(e))

    def update_snapshot_and_timestmap(
        self, snapshot_key, timestamp_key, write=True, **kwargs
    ):
        """Update snapshot and timestamp metadata.

        Args:
        - snapshot_key(str): snapshot key
        - timestamp_key(str): timestamp key
        - write(bool): (Optional) If True snapshot and timestamp metadata will be signed and written
        - kwargs(dict): (Optional) Expiration dates and intervals:
                        - snapshot_date(datetime)
                        - snapshot_interval(int)
                        - timestamp_date(datetime)
                        - timestamp_interval(int)

        Returns:
        None

        Raises:
        - InvalidKeyError: If wrong key is used to sign metadata
        - MetadataUpdateError: If any other error happened during metadata update
        """
        try:
            snapshot_date = kwargs.get("snapshot_date", datetime.datetime.now())
            snapshot_interval = kwargs.get("snapshot_interval", None)

            timestamp_date = kwargs.get("timestamp_date", datetime.datetime.now())
            timestamp_interval = kwargs.get("timestamp_interval", None)

            self.update_snapshot(
                snapshot_key, snapshot_date, snapshot_interval, write=write
            )
            self.update_timestamp(
                timestamp_key, timestamp_date, timestamp_interval, write=write
            )
        except (TUFError, SSLibError) as e:
            raise MetadataUpdateError("all", str(e))

    def update_targets_from_keystore(
        self, targets_key, start_date=datetime.datetime.now(), interval=None, write=True
    ):
        """Update targets metadata. Sign it with a key from the file system

        Args:
        - targets_key(securesystemslib.formats.RSAKEY_SCHEMA): Targets key.
        - start_date(datetime): Date to which the specified interval is added when
                                calculating expiration date. If a value is not
                                provided, it is set to the current time
        - interval(int): Number of days added to the start date. If not provided,
                        the default value is used
        - write(bool): If True timestmap metadata will be signed and written

        Returns:
        None

        Raises:
        - InvalidKeyError: If wrong key is used to sign metadata
        - TimestampMetadataUpdateError: If any other error happened during metadata update
        """
        try:
            self._try_load_metadata_key("targets", targets_key)
            self._update_metadata("targets", start_date, interval, write=write)
        except (TUFError, SSLibError) as e:
            raise TimestampMetadataUpdateError(str(e))

    def update_targets(
        self,
        targets_key_pin,
        targets_data=None,
        start_date=datetime.datetime.now(),
        interval=None,
        write=True,
        public_key=None,
    ):
        """Update target data, sign with smart card and write.

        Args:
        - targets_key_pin(str): Targets key pin
        - targets_data(dict): (Optional) Dictionary with targets data
        - start_date(datetime): Date to which the specified interval is added when
                                calculating expiration date. If a value is not
                                provided, it is set to the current time
        - interval(int): Number of days added to the start date. If not provided,
                        the default value is used
        - write(bool): If True targets metadata will be signed and written
        - public_key(securesystemslib.formats.RSAKEY_SCHEMA): RSA public key dict

        Returns:
        None

        Raises:
        - InvalidKeyError: If wrong key is used to sign metadata
        - MetadataUpdateError: If any other error happened during metadata update
        """
        try:
            if public_key is None:
                from taf.yubikey import get_piv_public_key_tuf

                public_key = get_piv_public_key_tuf()

            if not self.is_valid_metadata_yubikey("targets", public_key):
                raise InvalidKeyError("targets")

            if targets_data:
                self.add_targets(targets_data)

            self.set_metadata_expiration_date("targets", start_date, interval)

            self._repository.targets.add_external_signature_provider(
                public_key,
                partial(
                    targets_signature_provider, public_key["keyid"], targets_key_pin
                ),
            )
            if write:
                self._repository.write("targets")

        except (YubikeyError, TUFError, SSLibError) as e:
            raise TargetsMetadataUpdateError(str(e))

    def update_timestamp(
        self,
        timestamp_key,
        start_date=datetime.datetime.now(),
        interval=None,
        write=True,
    ):
        """Update timestamp metadata.

        Args:
        - timestamp_key
        - start_date(datetime): Date to which the specified interval is added when
                                calculating expiration date. If a value is not
                                provided, it is set to the current time
        - interval(int): Number of days added to the start date. If not provided,
                        the default value is used
        - write(bool): If True timestmap metadata will be signed and written

        Returns:
        None

        Raises:
        - InvalidKeyError: If wrong key is used to sign metadata
        - TimestampMetadataUpdateError: If any other error happened during metadata update
        """
        try:
            self._try_load_metadata_key("timestamp", timestamp_key)
            self._update_metadata("timestamp", start_date, interval, write=write)
        except (TUFError, SSLibError) as e:
            raise TimestampMetadataUpdateError(str(e))

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
