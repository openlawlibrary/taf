from logging import INFO
from typing import Optional
from logdecorator import log_on_start, log_on_end
from pathlib import Path
from taf.models.types import RolesKeysData
from taf.api.utils._conf import find_taf_directory
from taf.yubikey import get_and_validate_pin, setup, verify_yubikey_serial
from tuf.repository_tool import (
    generate_and_write_rsa_keypair,
    generate_and_write_unencrypted_rsa_keypair,
)
from securesystemslib import keys

from taf.api.roles import _initialize_roles_and_keystore
from taf.keys import get_key_name
from taf.log import taf_logger
from taf.models.types import RolesIterator
from taf.models.converter import from_dict
from ykman.piv import SLOT
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa


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


def get_yubikey_slot(role_name: str) -> str:
    """
    Maps a role name to a YubiKey PIV slot.

    Arguments:
        role_name: The name of the role (e.g., 'root', 'targets', 'snapshot', 'timestamp').

    Returns:
       An enum representing the YubiKey PIV slot.
    """
    role_slot_map = {
        "root": SLOT.AUTHENTICATION,
        "targets": SLOT.CARD_AUTH,
        "snapshot": SLOT.SIGNATURE,
        "timestamp": SLOT.SIGNATURE,
    }
    return role_slot_map.get(role_name.lower(), "9a")


def load_rsa_key_from_file(
    key_path: str, password: Optional[bytes] = None
) -> rsa.RSAPrivateKey:
    with open(key_path, "rb") as key_file:
        private_key = serialization.load_pem_private_key(
            key_file.read(),
            password=password,
        )
    return private_key


def generate_keys(
    auth_repo_path: Path, keystore: Optional[str], roles_key_infos: str
) -> None:
    if keystore is None:
        taf_directory = find_taf_directory(auth_repo_path)
        if taf_directory:
            keystore = str(taf_directory / "keystore")
        else:
            keystore = "./keystore"
    roles_key_infos_dict, keystore, _ = _initialize_roles_and_keystore(
        roles_key_infos, keystore
    )
    roles_keys_data = from_dict(roles_key_infos_dict, RolesKeysData)
    for role in RolesIterator(roles_keys_data.roles, include_delegations=True):
        for key_num in range(role.number):
            key_name = get_key_name(role.name, key_num, role.number)

            key_path = str(Path(keystore or "keystore", key_name))
            if keystore is not None:
                password = input(
                    "Enter keystore password and press ENTER (can be left empty): "
                )
                # Save the key to the file
                _generate_rsa_key(key_path, password, role.length)

                # Load the key from the file
                rsa_key = load_rsa_key_from_file(
                    key_path, password.encode() if password else None
                )
            else:
                rsa_key = keys.generate_rsa_key(role.length)
                private_key_val = rsa_key["keyval"]["private"]
                print(f"{role.name} key:\n\n{private_key_val}\n\n")

            if role.is_yubikey:
                print(
                    f"Generating RSA {role.length}-bit key on YubiKey for {role.name}"
                )
                slot_enum = get_yubikey_slot(role.name)
                if slot_enum is None:
                    print("Error: Invalid slot provided.")
                    continue
                # Collect the PIN for the YubiKey (input will be hidden)
                serial = verify_yubikey_serial()
                pin = get_and_validate_pin(f"{role.name} Key", serial=serial)

                # Use th existing setup function to generate the key on the YubiKey using the same key
                cert_cn = f"{role.name} Key"
                setup(
                    pin=pin,
                    cert_cn=cert_cn,
                    cert_exp_days=3650,
                    pin_retries=10,
                    private_key_pem=rsa_key.private_bytes(
                        encoding=serialization.Encoding.PEM,
                        format=serialization.PrivateFormat.TraditionalOpenSSL,
                        encryption_algorithm=serialization.NoEncryption(),
                    ),
                    serial=serial,
                )

                print(
                    f"Certificate successfully generated and stored on YubiKey in slot {slot_enum}"
                )
