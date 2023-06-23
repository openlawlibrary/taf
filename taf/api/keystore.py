from logging import DEBUG, INFO
from logdecorator import log_on_start, log_on_end
from pathlib import Path
from tuf.repository_tool import (
    generate_and_write_rsa_keypair,
    generate_and_write_unencrypted_rsa_keypair,
)

from taf.api.roles import _initialize_roles_and_keystore
from taf.constants import DEFAULT_ROLE_SETUP_PARAMS
from taf.keys import get_key_name
from taf.log import taf_logger


@log_on_start(DEBUG, "Generating '{key_path:s}'", logger=taf_logger)
@log_on_end(INFO, "Generated '{key_path:s}", logger=taf_logger)
def _generate_rsa_key(key_path, password, bits=None):
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


def generate_keys(keystore, roles_key_infos, delegated_roles_key_infos=None):
    """
    Generate public and private keys and writes them to disk. Names of keys correspond to names
    of TUF roles. If more than one key should be generated per role, a counter is appended
    to the role's name. E.g. root1, root2, root3 etc.

    Arguments:
        keystore: Location where the generated files should be saved
        roles_key_infos: A dictionary whose keys are role names, while values contain information about the keys.
            This includes:
                - passwords of the keystore files
                - number of keys per role (optional, defaults to one if not provided)
                - key length (optional, defaults to TUF's default value, which is 3072)
            Names of the keys are set to names of the roles plus a counter, if more than one key
            should be generated.
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
    if delegated_roles_key_infos is not None:
        roles_key_infos = delegated_roles_key_infos
        keystore = keystore or roles_key_infos.get("keystore")
    else:
        roles_key_infos, keystore = _initialize_roles_and_keystore(
            roles_key_infos, keystore
        )

    for role_name, key_info in roles_key_infos["roles"].items():
        num_of_keys = key_info.get("number", DEFAULT_ROLE_SETUP_PARAMS["number"])
        bits = key_info.get("length", DEFAULT_ROLE_SETUP_PARAMS["length"])
        passwords = key_info.get("passwords", [None] * num_of_keys)
        is_yubikey = key_info.get("yubikey", DEFAULT_ROLE_SETUP_PARAMS["yubikey"])
        for key_num in range(num_of_keys):
            if not is_yubikey:
                key_name = get_key_name(role_name, key_num, num_of_keys)
                key_path = str(Path(keystore, key_name))
                password = passwords[key_num]
                _generate_rsa_key(key_path, password, bits)
        if key_info.get("delegations"):
            delegations_info = {"roles": key_info["delegations"]}
            generate_keys(keystore, roles_key_infos, delegations_info)
