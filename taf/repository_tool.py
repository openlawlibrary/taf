import json
from fnmatch import fnmatch
from functools import partial, reduce
from pathlib import Path
from typing import Dict

import securesystemslib
import tuf.roledb
from securesystemslib.exceptions import Error as SSLibError
from securesystemslib.interface import import_rsa_privatekey_from_file
from tuf.exceptions import Error as TUFError
from tuf.repository_tool import (
    import_rsakey_from_pem,
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
    TargetsMetadataUpdateError,
    TimestampMetadataUpdateError,
    YubikeyError,
    KeystoreError,
)
from taf.git import GitRepository
from taf.utils import (
    normalize_file_line_endings,
)
from taf import YubikeyMissingLibrary
try:
    import taf.yubikey as yk
except ImportError:
    yk = YubikeyMissingLibrary()  # type: ignore



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
