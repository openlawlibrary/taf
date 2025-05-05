from logging import DEBUG, ERROR
from typing import Dict, Optional
import click

from pathlib import Path
from logdecorator import log_on_end, log_on_error, log_on_start
from taf.auth_repo import AuthenticationRepository
from taf.constants import DEFAULT_RSA_SIGNATURE_SCHEME
from taf.exceptions import TAFError, YubikeyError

# from taf.constants import DEFAULT_RSA_SIGNATURE_SCHEME
from taf.log import taf_logger
from taf.tuf.keys import get_sslib_key_from_value
from taf.tuf.repository import MAIN_ROLES
import taf.yubikey.yubikey as yk
from taf.yubikey.yubikey_manager import PinManager


@log_on_start(DEBUG, "Exporting public pem from YubiKey", logger=taf_logger)
@log_on_end(DEBUG, "Exported public pem from YubuKey", logger=taf_logger)
@log_on_error(
    ERROR,
    "An error occurred while exporting public pem from YubiKey: {e}",
    logger=taf_logger,
    on_exceptions=TAFError,
    reraise=True,
)
def export_yk_public_pem(
    path: Optional[str] = None, serial: Optional[str] = None
) -> None:
    """
    Export public key from a YubiKey and save it to a file or print to console.

    Arguments:
        path (optional): Path to a file to which the public key should be written.
        The key is printed to console if file path is not provided.

    Side Effects:
       Write public key to a file if path is specified

    Returns:
        None
    """
    try:
        serials = [serial] if serial else yk.get_serial_nums()

        if not len(serials):
            print("YubiKey not inserted.")
            return

        for serial in serials:
            pub_key = yk.get_piv_public_key_tuf(serial=serial)
            keyid = yk._get_legacy_keyid(pub_key)
            pub_key_pem = pub_key.keyval["public"]
            if path is None:
                print(f"Serial: {serial}")
                print(f"Key id: {keyid}")
                print(pub_key_pem)
            else:
                if not path.endswith(".pub"):
                    path = f"{path}.pub"
                pem_path = Path(path)
                parent = pem_path.parent
                parent.mkdir(parents=True, exist_ok=True)
                pem_path.write_text(pub_key_pem)
    except Exception:
        print("Could not export the public key. Check if a YubiKey is inserted")
        return


@log_on_start(DEBUG, "Exporting certificate from YubiKey", logger=taf_logger)
@log_on_end(DEBUG, "Exported certificate from YubuKey", logger=taf_logger)
@log_on_error(
    ERROR,
    "An error occurred while exporting certificate from YubiKey: {e}",
    logger=taf_logger,
    on_exceptions=TAFError,
    reraise=True,
)
def export_yk_certificate(
    path: Optional[str] = None, serial: Optional[str] = None
) -> None:
    """
    Export certificate from the YubiKey.

    Arguments:
        path (optional): Path to a file to which the certificate key should be written.
        Will be written to the user's home directory by default

    Side Effects:
       Write certificate to a file

    Returns:
        None
    """
    try:
        serials = [serial] if serial else yk.get_serial_nums()

        if not len(serials):
            print("YubiKey not inserted.")
            return
        for serial in serials:
            pub_key_pem = yk.export_piv_pub_key(serial=serial).decode("utf-8")
            scheme = DEFAULT_RSA_SIGNATURE_SCHEME
            key = get_sslib_key_from_value(pub_key_pem, scheme)
            yk.export_yk_certificate(path, key, serial)
    except Exception as e:
        print(e)
        print("Could not export certificate. Check if a YubiKey is inserted")
        return


@log_on_start(DEBUG, "Listing roles of inserted YubiKesy", logger=taf_logger)
@log_on_error(
    ERROR,
    "An error occurred while listing roles of inserted YubiKeys: {e}",
    logger=taf_logger,
    on_exceptions=TAFError,
    reraise=True,
)
def get_yk_roles(path: str, serial: Optional[str] = None) -> Dict:
    """
    List all roles that the inserted YubiKey whose metadata files can be signed by this YubiKey.
    In case of delegated targets roles, include the delegation paths.

    Arguments:
        path: Authentication repository's path.
    Side Effects:
        None

    Returns:
        A dictionary containing roles and delegated paths in case of delegated target roles
    """
    serials = [serial] if serial else yk.get_serial_nums()
    roles_per_yubikes: Dict = {}

    if not len(serials):
        print("YubiKey not inserted.")
        return roles_per_yubikes

    auth = AuthenticationRepository(path=path)
    for serial in serials:
        pub_key = yk.get_piv_public_key_tuf(serial=serial)
        roles = auth.find_associated_roles_of_key(pub_key)
        roles_with_paths: Dict = {role: {} for role in roles}
        for role in roles:
            if role not in MAIN_ROLES:
                roles_with_paths[role] = auth.get_role_paths(role)
        roles_per_yubikes[serial] = roles_with_paths
    return roles_per_yubikes


@log_on_start(DEBUG, "Setting up a new signing YubiKey", logger=taf_logger)
@log_on_end(DEBUG, "Finished setting up a new signing YubiKey", logger=taf_logger)
@log_on_error(
    ERROR,
    "An error occurred while setting up a new YubiKey: {e}",
    logger=taf_logger,
    on_exceptions=TAFError,
    reraise=True,
)
def setup_signing_yubikey(
    pin_manager: PinManager, certs_dir: Optional[str] = None, key_size: int = 2048
) -> None:
    """
    Delete everything from the inserted YubiKey, generate a new key and copy it to the YubiKey.
    Optionally export and save the certificate to a file.

    Arguments:
        certs_dir (optional): Path to a directory where the exported certificate should be stored.

    Side Effects:
       None

    Returns:
        None
    """
    if not click.confirm(
        "WARNING - this will delete everything from the inserted key. Proceed?"
    ):
        return
    yubikeys = yk.yubikey_prompt(
        ["new Yubikey"],
        pin_manager=pin_manager,
        creating_new_key=True,
        pin_confirm=True,
        pin_repeat=True,
        prompt_message="Please insert the new Yubikey and press ENTER",
    )
    if yubikeys:
        _, serial_num, _ = yubikeys[0]
        key = yk.setup_new_yubikey(pin_manager, serial_num, key_size=key_size)
        yk.export_yk_certificate(certs_dir, key, serial_num)
    else:
        raise YubikeyError("Could not generate a new key")


@log_on_start(DEBUG, "Setting up a new test YubiKey", logger=taf_logger)
@log_on_end(DEBUG, "Finished setting up a test YubiKey", logger=taf_logger)
@log_on_error(
    ERROR,
    "An error occurred while setting up a test YubiKey: {e}",
    logger=taf_logger,
    on_exceptions=TAFError,
)
def setup_test_yubikey(
    pin_manager: PinManager,
    key_path: str,
    key_size: Optional[int] = 2048,
    serial: Optional[str] = None,
) -> None:
    """
    Reset the inserted yubikey, set default pin and copy the specified key
    to it.

    Arguments:
        key_path: Path to a key which should be copied to a YubiKey.

    Side Effects:
       None

    Returns:
        None
    """
    if serial is None:
        serials = yk.get_serial_nums()
        if not len(serials):
            raise YubikeyError("YubiKey not inserted")
        if len(serials) > 1:
            raise YubikeyError("Insert only one YubiKey")

    if not click.confirm("WARNING - this will reset the inserted key. Proceed?"):
        return

    serial = serials[0]
    key_pem_path = Path(key_path)
    key_pem = key_pem_path.read_bytes()

    print(f"Importing RSA private key from {key_path} to Yubikey...")
    pin = yk.DEFAULT_PIN
    pin_manager.add_pin(serial, pin)

    pub_key = yk.setup(
        pin, serial, "Test Yubikey", private_key_pem=key_pem, key_size=key_size
    )
    print("\nPrivate key successfully imported.\n")
    print("\nPublic key (PEM): \n{}".format(pub_key.decode("utf-8")))
    print("Pin: {}\n".format(pin))
