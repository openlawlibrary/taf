import click
from logging import INFO
from typing import Dict, Optional, Union
from logdecorator import log_on_start, log_on_end
from pathlib import Path
from taf.models.types import RolesKeysData
from taf.api.utils._conf import find_taf_directory

from taf.api.roles import initialize_roles_and_keystore
from taf.signers.keystore import check_keystore_path_usable_in_uri, get_key_name
from taf.log import taf_logger
from taf.models.types import RolesIterator
from taf.models.converter import from_dict
from taf.exceptions import KeystoreError
from taf.tuf.keys import generate_and_write_keypair


@log_on_start(INFO, "Generating '{key_path:s}'", logger=taf_logger)
@log_on_end(INFO, "Generated '{key_path:s}", logger=taf_logger)
def _generate_key(
    key_path: str, scheme: Optional[str], rsa_key_size: Optional[int] = None
) -> None:
    """
    Generate public and private key

    Arguments:
        key_path: The path to write the private key to.
        scheme: Signing scheme, which decides the key type.
        rsa_key_size (optional): The number of bits of an RSA key. Not used for other key types.

    Raises:
        KeystoreError: The key could not be generated or written.

    Side Effects:
        Writes key files to disk.
        Overwrites files if they already exist.

    Returns:
        None
    """
    try:
        generate_and_write_keypair(key_path, scheme, rsa_key_size)
        taf_logger.log("NOTICE", f"Generated key {key_path}")
    except Exception as e:
        raise KeystoreError(
            f"An error occurred while generating key {key_path}: {e}"
        ) from e


def generate_keys(
    keystore: Optional[Union[str, Path]], roles_key_infos: Optional[Union[str, Dict]]
) -> None:
    """
    Generate public and private keys and writes them to disk. Names of keys correspond to names
    of TUF roles. If more than one key should be generated per role, a counter is appended
    to the role's name. E.g. root1, root2, root3 etc.

    Arguments:
        keystore: Location where the generated files should be saved
        roles_key_infos: Path to a json file, or a dictionary, which contains information about repository's roles and keys.
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
    if keystore is None:
        raise KeystoreError("No keystore to write the keys to")

    roles_keys_data = from_dict(roles_key_infos_dict, RolesKeysData)
    for role in RolesIterator(roles_keys_data.roles, include_delegations=True):
        if not role.is_yubikey:
            for key_num in range(role.number):
                key_name = get_key_name(role.name, key_num, role.number)
                key_path = Path(keystore, key_name)
                check_keystore_path_usable_in_uri(key_path)
                if key_path.exists() and not click.confirm(
                    f"{key_path} already exists. Overwrite it?"
                ):
                    continue
                _generate_key(str(key_path), role.scheme, role.length)
