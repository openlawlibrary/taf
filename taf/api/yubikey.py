import click

from pathlib import Path
import taf.yubikey as yk


def export_yk_public_pem(path=None):
    """
    Export public key from a YubiKey and save it to a file or print to console.

    Arguments:
        path (optional): Path to a file to which the public key should be written.
        The key is printed to console if file path is not provided.

    Side Effects:
       None

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


def setup_signing_yubikey(certs_dir=None):
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


def setup_test_yubikey(key_path):
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
