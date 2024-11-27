import glob
import re
from getpass import getpass
from os import getcwd
from pathlib import Path
from typing import List, Optional
import click
import securesystemslib
from taf.tuf.keys import (
    load_public_key_from_file,
    load_signer_from_file,
    load_signer_from_pem,
)

from taf.constants import DEFAULT_RSA_SIGNATURE_SCHEME
from taf.exceptions import KeystoreError

from taf.tuf.repository import MetadataRepository as TUFRepository

from securesystemslib.signer._crypto_signer import CryptoSigner

from securesystemslib.signer._key import SSlibKey


def default_keystore_path() -> str:
    keystore_path = str(Path(getcwd(), "keystore"))
    return keystore_path


def get_keystore_keys_of_role(keystore: str, role: str) -> List[str]:
    keystores_glob = f"{keystore}/{role}*"
    # Use glob to find matching files
    keystores = glob.glob(keystores_glob)
    pattern = r"^{}(?:\d+)?$".format(re.escape(role))

    # Iterate over the matching files
    return [
        Path(keystore_path).name
        for keystore_path in keystores
        if re.match(pattern, Path(keystore_path).name)
    ]


def _form_private_pem(pem: str) -> str:
    return f"-----BEGIN RSA PRIVATE KEY-----\n{pem}\n-----END RSA PRIVATE KEY-----"


def _from_public_pem(pem: str) -> str:
    return f"-----BEGIN PUBLIC KEY-----\n{pem}\n-----END PUBLIC KEY-----"


def key_cmd_prompt(
    key_name: str,
    role: str,
    taf_repo: TUFRepository,
    loaded_keys: Optional[List] = None,
    scheme: Optional[str] = DEFAULT_RSA_SIGNATURE_SCHEME,
) -> CryptoSigner:
    def _enter_and_check_key(key_name, role, loaded_keys, scheme):
        pem = getpass(f"Enter {key_name} private key without its header and footer\n")
        pem = _form_private_pem(pem)
        try:
            signer = load_signer_from_pem(pem, scheme)
        except Exception:
            print("Invalid key")
            return None
        public_key = signer.public_key
        if not taf_repo.is_valid_metadata_yubikey(role, public_key):
            print(f"The entered key is not a valid {role} key")
            return None
        if loaded_keys is not None and public_key in loaded_keys:
            print("Key already entered")
            return None
        return signer

    while True:
        pem = _enter_and_check_key(key_name, role, loaded_keys, scheme)
        if pem is not None:
            return pem


def new_public_key_cmd_prompt(scheme: Optional[str]) -> SSlibKey:
    def _enter_and_check_key(scheme):
        pem = getpass("Enter public key without its header and footer\n")
        pem = _from_public_pem(pem)
        try:
            return load_public_key_from_file(pem, scheme)
        except Exception:
            print("Invalid key")
            return None

    while True:
        key = _enter_and_check_key(scheme)
        if key is not None:
            return key


def load_signer_from_private_keystore(
    keystore: str,
    key_name: str,
    scheme: Optional[str] = DEFAULT_RSA_SIGNATURE_SCHEME,
    password: Optional[str] = None,
) -> CryptoSigner:
    key_path = Path(keystore, key_name).expanduser().resolve()
    if not key_path.is_file():
        raise KeystoreError(f"{str(key_path)} does not exist")

    def _read_key(path, password, scheme):
        def _read_key_or_keystore_error(path, password, scheme):
            try:
                return load_signer_from_file(path, password or None, scheme=scheme)
            except TypeError:
                raise
            except Exception as e:
                raise KeystoreError(e)

        try:
            # try to load with a given password or None
            return _read_key_or_keystore_error(path, password, scheme)
        except TypeError:
            password = getpass(
                f"Enter {key_name} keystore file password and press ENTER"
            )
            try:
                return _read_key_or_keystore_error(path, password, scheme)
            except Exception:
                return None
        except Exception:
            return None

    while True:
        signer = _read_key(key_path, password, scheme)
        if signer is not None:
            return signer
        if not click.confirm(f"Could not open keystore file {key_path}. Try again?"):
            raise KeystoreError(f"Could not open keystore file {key_path}")


def read_public_key_from_keystore(
    keystore: str, key_name: str, scheme: Optional[str] = DEFAULT_RSA_SIGNATURE_SCHEME
) -> SSlibKey:
    pub_key_path = Path(keystore, f"{key_name}.pub").expanduser().resolve()
    if not pub_key_path.is_file():
        raise KeystoreError(f"{str(pub_key_path)} does not exist")
    try:
        return load_public_key_from_file(str(pub_key_path), scheme)
    except (
        securesystemslib.exceptions.FormatError,
        securesystemslib.exceptions.Error,
    ) as e:
        raise KeystoreError(e)
