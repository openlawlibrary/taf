import glob
import re
from os import getcwd
from pathlib import Path
from typing import List, Optional, Union
import click
import securesystemslib
from taf.tuf.keys import load_public_key_from_file

from taf.exceptions import KeystoreError
from taf.tuf.signer_uris import import_keystore_key, keystore_uri, load_signer

from securesystemslib.signer import Signer

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


def load_signer_from_keystore_uri(
    keystore: Union[str, Path], key_name: str, public_keys: List[SSlibKey]
) -> Optional[Signer]:
    """Build a signer for a keystore file from its URI. The file does not say
    which of the role's keys it holds, so each one is tried. Return None if
    none match."""
    uri = keystore_uri(keystore, key_name)
    while True:
        try:
            return load_signer(uri, public_keys)
        except Exception as e:
            print(f"Could not open keystore file {uri}: {e}")
        if not click.confirm("Try again?"):
            raise KeystoreError(f"Could not open keystore file {uri}")


def load_signer_from_private_keystore(
    keystore: Union[str, Path], key_name: str, scheme: Optional[str] = None
) -> Signer:
    """Load a keystore key that is not in metadata yet, through its URI"""
    key_path = Path(keystore, key_name).expanduser().resolve()
    if not key_path.is_file():
        raise KeystoreError(f"{str(key_path)} does not exist")

    while True:
        try:
            uri, public_key = import_keystore_key(keystore, key_name, scheme)
            signer = load_signer(uri, [public_key])
            if signer is not None:
                return signer
            raise KeystoreError(f"{uri} does not match its public key")
        except Exception as e:
            print(f"Could not open keystore file {key_path}: {e}")
        if not click.confirm("Try again?"):
            raise KeystoreError(f"Could not open keystore file {key_path}")


def read_public_key_from_keystore(keystore: str, key_name: str) -> SSlibKey:
    pub_key_path = Path(keystore, f"{key_name}.pub").expanduser().resolve()
    if not pub_key_path.is_file():
        raise KeystoreError(f"{str(pub_key_path)} does not exist")
    try:
        return load_public_key_from_file(str(pub_key_path))
    except (
        securesystemslib.exceptions.FormatError,
        securesystemslib.exceptions.Error,
    ) as e:
        raise KeystoreError(e)
