"""Private key URIs of signing keys, and loading signers from them.

Every signer is built through securesystemslib's ``Signer.from_priv_key_uri``,
which picks the signer class from the URI's prefix.
"""

from pathlib import Path
from typing import List, Optional, Union
from urllib import parse

from cryptography.hazmat.primitives.serialization import load_pem_private_key

from securesystemslib.exceptions import KeyMismatchError
from securesystemslib.signer import (
    CryptoSigner,
    SecretsHandler,
    Signer,
    SSlibKey,
)

from taf.exceptions import KeystoreError

# importing YkSigner registers its "yk" prefix
from taf.tuf.keys import YkSigner, _from_crypto


def check_keystore_path_usable_in_uri(path: Union[str, Path]) -> None:
    """Raise KeystoreError if a keystore file's path can't be used in a URI.
    A URI ends at '#' or '?', so it would point to another file."""
    path = Path(path).expanduser().resolve()
    if "#" in str(path) or "?" in str(path):
        raise KeystoreError(f"Keystore path {path} can't contain '#' or '?'")


def get_keystore_uri(keystore: Union[str, Path], key_name: str) -> str:
    path = Path(keystore, key_name).expanduser().resolve()
    check_keystore_path_usable_in_uri(path)
    return f"{CryptoSigner.SCHEME}:{path.as_posix()}"


def create_signer_from_keystore_file(
    keystore: Union[str, Path], key_name: str, scheme: Optional[str] = None
) -> Signer:
    """Create the signer of a keystore file whose key is not in metadata yet.
    The key file is read once to get its public part, which the signer needs."""
    path = Path(keystore, key_name).expanduser().resolve()
    private_key = load_pem_private_key(path.read_bytes(), None)
    public_key = _from_crypto(private_key.public_key(), scheme)
    return Signer.from_priv_key_uri(get_keystore_uri(keystore, key_name), public_key)


def get_yubikey_uri(serial_num: int, slot: Optional[int], key_name: str) -> str:
    params = {"name": key_name}
    if slot is not None:
        params["slot"] = f"{int(slot):x}"
    return f"{YkSigner.SCHEME}:{serial_num}?{parse.urlencode(params)}"


def load_signer(
    uri: str,
    public_keys: List[SSlibKey],
    secrets_handler: Optional[SecretsHandler] = None,
) -> Optional[Signer]:
    """Return a signer for the first of ``public_keys`` that matches the
    private key, or None. Keystore keys are checked by securesystemslib.
    YubiKey keys are not checked here, so pass only the key read from the
    device."""
    for public_key in public_keys:
        try:
            return Signer.from_priv_key_uri(uri, public_key, secrets_handler)
        except (KeyMismatchError, ValueError):
            continue
    return None
