import glob
import re
from os import getcwd
from pathlib import Path
from typing import List, Optional, Union
import click

from taf.exceptions import KeystoreError, SchemeNotSpecifiedError
from taf.tuf.signer_uris import (
    get_keystore_uri,
    create_signer_from_keystore_file,
    load_signer,
)

from securesystemslib.signer import Signer

from securesystemslib.signer._key import SSlibKey


def default_keystore_path() -> str:
    keystore_path = str(Path(getcwd(), "keystore"))
    return keystore_path


def get_key_name(role_name: str, key_num: int, num_of_keys: int) -> str:
    """
    Return a keystore key's name based on the role's name and total number of signing keys,
    as well as the specified counter. If number of signing keys is one, return the role's name.
    If the number of signing keys is greater that one, return role's name + counter (root1, root2...)
    """
    if num_of_keys == 1:
        return role_name
    else:
        return role_name + str(key_num + 1)


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
    """Build a signer for a keystore file from its URI, for the first of
    public_keys that the file holds. Return None if none match."""
    uri = get_keystore_uri(keystore, key_name)

    def _read_key(uri, public_keys):
        try:
            return load_signer(uri, public_keys), None
        except Exception as e:
            return None, e

    while True:
        signer, error = _read_key(uri, public_keys)
        if error is None:
            return signer
        if not click.confirm(
            f"Could not open keystore file {uri}: {error}. Try again?"
        ):
            raise KeystoreError(f"Could not open keystore file {uri}")


def load_signer_from_private_keystore(
    keystore: Union[str, Path], key_name: str, scheme: Optional[str] = None
) -> Signer:
    """Load a keystore key that is not in metadata yet, through its URI"""
    key_path = Path(keystore, key_name).expanduser().resolve()
    if not key_path.is_file():
        raise KeystoreError(f"{str(key_path)} does not exist")

    def _read_key(keystore, key_name, scheme):
        try:
            return create_signer_from_keystore_file(keystore, key_name, scheme), None
        except SchemeNotSpecifiedError:
            raise
        except Exception as e:
            return None, e

    while True:
        signer, error = _read_key(keystore, key_name, scheme)
        if signer is not None:
            return signer
        if not click.confirm(
            f"Could not open keystore file {key_path}: {error}. Try again?"
        ):
            raise KeystoreError(f"Could not open keystore file {key_path}")
