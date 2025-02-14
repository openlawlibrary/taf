from logging import INFO
from typing import Optional, Union
from logdecorator import log_on_start, log_on_end
from pathlib import Path
from taf.models.types import RolesKeysData
from taf.api.utils._conf import find_taf_directory

from taf.api.roles import initialize_roles_and_keystore
from taf.keys import get_key_name
from taf.log import taf_logger
from taf.models.types import RolesIterator
from taf.models.converter import from_dict
from taf.exceptions import KeystoreError
from taf.tuf.keys import generate_and_write_rsa_keypair, generate_rsa_keypair


@log_on_start(INFO, "Generating '{key_path:s}'", logger=taf_logger)
@log_on_end(INFO, "Generated '{key_path:s}", logger=taf_logger)
def _generate_rsa_key(key_path: str, password: str, bits: Optional[int] = None) -> None:
    """
    Generate public and private key

    Arguments:
        key_path (optional): The path to write the private key to.
        password (optional): An encryption password.
        bits (optional): The number of bits of the generated RSA key.

    Raises:
        UnsupportedLibraryError: pyca/cryptography is not available.
        FormatError: Arguments are malformed.
        StorageError: Key files cannot be written.

    Side Effects:
        Writes key files to disk.
        Overwrites files if they already exist.

    Returns:
        None
    """
    try:
        generate_and_write_rsa_keypair(path=key_path, key_size=bits, password=password)
        taf_logger.log("NOTICE", f"Generated key {key_path}")
    except Exception:
        taf_logger.error(f"An error occurred while generating rsa key {key_path}")
        raise KeystoreError(f"An error occurred while generating rsa key {key_path}")


def generate_keys(
    keystore: Optional[Union[str, Path]], roles_key_infos: Optional[str]
) -> None:
    """
    Generate public and private keys and writes them to disk. Names of keys correspond to names
    of TUF roles. If more than one key should be generated per role, a counter is appended
    to the role's name. E.g. root1, root2, root3 etc.

    Arguments:
        keystore: Location where the generated files should be saved
        roles_key_infos: Path to a json file which contains information about repository's roles and keys.
    Raises:
        UnsupportedLibraryError: pyca/cryptography is not available.
        FormatError: One or more keys not properly specified
        StorageError: Key files cannot be written.

    Side Effects:
        Writes key files to disk.
        Overwrites files if they already exist.

    Returns:
        None

    Raises:
        KeystoreError if an error occurs while initializing the keystore directory or generating a key
    """
    # TODO handle scheme
    if keystore is None:
        taf_directory = find_taf_directory(Path())
        if taf_directory:
            keystore = str(taf_directory / "keystore")
        else:
            keystore = "./keystore"

    taf_logger.log("NOTICE", f"Generating keys in {str(Path(keystore).absolute())}")
    roles_key_infos_dict, keystore, _ = initialize_roles_and_keystore(
        roles_key_infos, str(keystore)
    )

    roles_keys_data = from_dict(roles_key_infos_dict, RolesKeysData)
    for role in RolesIterator(roles_keys_data.roles, include_delegations=True):
        if not role.is_yubikey:
            for key_num in range(role.number):
                key_name = get_key_name(role.name, key_num, role.number)
                if keystore is not None:
                    password = input(
                        f"Enter {key_name} keystore password and press ENTER (can be left empty)"
                    )
                    key_path = str(Path(keystore, key_name))
                    _generate_rsa_key(key_path, password, role.length)
                else:
                    rsa_key, _ = generate_rsa_keypair(role.length)
                    print(f"{role.name} key:\n\n{rsa_key.decode()}\n\n")
