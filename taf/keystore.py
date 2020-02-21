from getpass import getpass
from pathlib import Path

import click
import securesystemslib
from securesystemslib.interface import (
    import_rsa_privatekey_from_file,
    import_rsa_publickey_from_file,
)
from tuf.repository_tool import import_rsakey_from_pem

from taf.constants import DEFAULT_RSA_SIGNATURE_SCHEME
from taf.exceptions import KeystoreError


def _form_private_pem(pem):
    return f"-----BEGIN RSA PRIVATE KEY-----\n{pem}\n-----END RSA PRIVATE KEY-----"


def _from_public_pem(pem):
    return f"-----BEGIN PUBLIC KEY-----\n{pem}\n-----END PUBLIC KEY-----"


def key_cmd_prompt(
    key_name, role, taf_repo, loaded_keys=None, scheme=DEFAULT_RSA_SIGNATURE_SCHEME
):
    def _enter_and_check_key(key_name, role, loaded_keys, scheme):
        pem = getpass(f"Enter {key_name} private key without its header and footer\n")
        pem = _form_private_pem(pem)
        try:
            key = import_rsakey_from_pem(pem, scheme)
        except Exception:
            print("Invalid key")
            return None
        public_key = import_rsakey_from_pem(key["keyval"]["public"], scheme)
        if not taf_repo.is_valid_metadata_yubikey(role, public_key):
            print(f"The entered key is not a valid {role} key")
            return None
        if loaded_keys is not None and key in loaded_keys:
            print("Key already entered")
            return None
        return key

    while True:
        key = _enter_and_check_key(key_name, role, loaded_keys, scheme)
        if key is not None:
            return key


def load_tuf_private_key(key_str, key_name, scheme=DEFAULT_RSA_SIGNATURE_SCHEME):
    if not key_str:
        key_str = getpass(
            f"Enter {key_name} private key without its header and footer\n"
        )
    key_pem = _form_private_pem(key_str)

    return import_rsakey_from_pem(key_pem, scheme)


def new_public_key_cmd_prompt(scheme):
    def _enter_and_check_key(scheme):
        pem = getpass(f"Enter public key without its header and footer\n")
        pem = _from_public_pem(pem)
        try:
            key = import_rsakey_from_pem(pem, scheme)
        except Exception:
            print("Invalid key")
            return None
        return import_rsakey_from_pem(key["keyval"]["public"], scheme)

    while True:
        key = _enter_and_check_key(scheme)
        if key is not None:
            return key


def read_private_key_from_keystore(
    keystore,
    key_name,
    roles_key_info=None,
    key_num=None,
    scheme=DEFAULT_RSA_SIGNATURE_SCHEME,
    password=None,
):
    key_path = Path(keystore, key_name)
    if not key_path.is_file():
        raise KeystoreError(f"{str(key_path)} does not exist")

    if password is not None and roles_key_info is not None:
        passwords = roles_key_info.get("passwords")
        if passwords is not None and len(passwords):
            password = passwords[key_num]

    def _read_key(path, password, scheme):
        def _read_key_or_keystore_error(path, password, scheme):
            try:
                return import_rsa_privatekey_from_file(
                    str(Path(keystore, key_name)), password or None, scheme=scheme
                )
            except (
                securesystemslib.exceptions.FormatError,
                securesystemslib.exceptions.Error,
            ) as e:
                if "password" in str(e).lower():
                    return None
                raise KeystoreError(e)

        try:
            # try to load with a given password or None
            return _read_key_or_keystore_error(path, password, scheme)
        except securesystemslib.exceptions.CryptoError:
            password = getpass(
                f"Enter {key_name} keystore file password and press ENTER"
            )
            return _read_key_or_keystore_error(path, password, scheme)
        except Exception:
            return None

    while True:
        key = _read_key(key_path, password, scheme)
        if key is not None:
            return key
        if not click.confirm("Could not open keystore file. Try again?"):
            raise KeystoreError(f"Could not open keystore file {key_path}")


def read_public_key_from_keystore(
    keystore, key_name, scheme=DEFAULT_RSA_SIGNATURE_SCHEME
):
    pub_key_path = Path(keystore, f"{key_name}.pub")
    if not pub_key_path.is_file():
        raise KeystoreError(f"{str(pub_key_path)} does not exist")
    try:
        return import_rsa_publickey_from_file(str(pub_key_path), scheme)
    except (
        securesystemslib.exceptions.FormatError,
        securesystemslib.exceptions.Error,
    ) as e:
        raise KeystoreError(e)
