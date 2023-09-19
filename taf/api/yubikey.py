from logging import DEBUG, ERROR
from typing import Optional
import click

from pathlib import Path
from logdecorator import log_on_end, log_on_error, log_on_start
from taf.exceptions import TAFError
from tuf.repository_tool import import_rsakey_from_pem

from taf.constants import DEFAULT_RSA_SIGNATURE_SCHEME
from taf.log import taf_logger
import taf.yubikey as yk


@log_on_start(DEBUG, "Exporting public pem from YubiKey", logger=taf_logger)
@log_on_end(DEBUG, "Exported public pem from YubuKey", logger=taf_logger)
@log_on_error(
    ERROR,
    "An error occurred while exporting public pem from YubiKey: {e}",
    logger=taf_logger,
    on_exceptions=TAFError,
    reraise=True,
)
def export_yk_public_pem(path: Optional[str] = None) -> None:
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
        pub_key_pem = yk.export_piv_pub_key().decode("utf-8")
    except Exception:
        print("Could not export the public key. Check if a YubiKey is inserted")
        return
    if path is None:
        print(pub_key_pem)
    else:
        if not path.endswith(".pub"):
            path = f"{path}.pub"
        path = Path(path)
        parent = path.parent
        parent.mkdir(parents=True, exist_ok=True)
        path.write_text(pub_key_pem)


@log_on_start(DEBUG, "Exporting certificate from YubiKey", logger=taf_logger)
@log_on_end(DEBUG, "Exported certificate from YubuKey", logger=taf_logger)
@log_on_error(
    ERROR,
    "An error occurred while exporting certificate from YubiKey: {e}",
    logger=taf_logger,
    on_exceptions=TAFError,
    reraise=True,
)
def export_yk_certificate(path: Optional[str] = None) -> None:
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
        pub_key_pem = yk.export_piv_pub_key().decode("utf-8")
        scheme = DEFAULT_RSA_SIGNATURE_SCHEME
        key = import_rsakey_from_pem(pub_key_pem, scheme)
        yk.export_yk_certificate(path, key)
    except Exception:
        print("Could not export certificate. Check if a YubiKey is inserted")
        return


@log_on_start(DEBUG, "Setting up a new signing YubiKey", logger=taf_logger)
@log_on_end(DEBUG, "Finished setting up a new signing YubiKey", logger=taf_logger)
@log_on_error(
    ERROR,
    "An error occurred while setting up a new YubiKey: {e}",
    logger=taf_logger,
    on_exceptions=TAFError,
    reraise=True,
)
def setup_signing_yubikey(certs_dir: Optional[str] = None) -> None:
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
    _, serial_num = yk.yubikey_prompt(
        "new Yubikey",
        creating_new_key=True,
        pin_confirm=True,
        pin_repeat=True,
        prompt_message="Please insert the new Yubikey and press ENTER",
    )
    key = yk.setup_new_yubikey(serial_num)
    yk.export_yk_certificate(certs_dir, key)


@log_on_start(DEBUG, "Setting up a new test YubiKey", logger=taf_logger)
@log_on_end(DEBUG, "Finished setting up a test YubiKey", logger=taf_logger)
@log_on_error(
    ERROR,
    "An error occurred while setting up a test YubiKey: {e}",
    logger=taf_logger,
    on_exceptions=TAFError,
    reraise=True,
)
def setup_test_yubikey(key_path: str) -> None:
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
    if not click.confirm("WARNING - this will reset the inserted key. Proceed?"):
        return
    key_path = Path(key_path)
    key_pem = key_path.read_bytes()

    print(f"Importing RSA private key from {key_path} to Yubikey...")
    pin = yk.DEFAULT_PIN

    pub_key = yk.setup(pin, "Test Yubikey", private_key_pem=key_pem)
    print("\nPrivate key successfully imported.\n")
    print("\nPublic key (PEM): \n{}".format(pub_key.decode("utf-8")))
    print("Pin: {}\n".format(pin))
