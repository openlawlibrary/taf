from logging import INFO
from typing import Optional
from logdecorator import log_on_start, log_on_end
from pathlib import Path
from taf.models.types import RolesKeysData
from tuf.repository_tool import (
    generate_and_write_rsa_keypair,
    generate_and_write_unencrypted_rsa_keypair,
)

from taf.api.roles import _initialize_roles_and_keystore
from taf.keys import get_key_name
from taf.log import taf_logger
from taf.models.types import RolesIterator
from taf.models.converter import from_dict


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
    if password:
        generate_and_write_rsa_keypair(filepath=key_path, bits=bits, password=password)
    else:
        generate_and_write_unencrypted_rsa_keypair(filepath=key_path, bits=bits)


def generate_keys(keystore: str, roles_key_infos: str) -> None:
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
    """
    roles_key_infos, keystore = _initialize_roles_and_keystore(
        roles_key_infos, keystore
    )

    roles_keys_data = from_dict(roles_key_infos, RolesKeysData)
    for role in RolesIterator(roles_keys_data.roles, include_delegations=False):
        if not role.is_yubikey:
            for key_num in range(role.number):
                key_name = get_key_name(role.name, key_num, role.number)
                key_path = str(Path(keystore, key_name))
                password = input(
                    "Enter keystore password and press ENTER (can be left empty)"
                )
                _generate_rsa_key(key_path, password, role.length)
