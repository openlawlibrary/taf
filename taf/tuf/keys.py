"""TUF metadata key functions.

"""


from typing import Optional

from pathlib import Path
from securesystemslib.signer import SSlibKey, CryptoSigner
from securesystemslib.formats import encode_canonical
from securesystemslib.hash import digest

from cryptography.hazmat.primitives.serialization import (
    load_pem_private_key,
    load_pem_public_key,
)
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPublicKey


def _get_legacy_keyid(key: SSlibKey) -> str:
    """Computes legacy keyid as hash over an opinionated canonical
    representation of the public key."""
    data = encode_canonical(
        {
            "keytype": key.keytype,
            "scheme": key.scheme,
            "keyval": {"public": key.keyval["public"].strip()},
            "keyid_hash_algorithms": ["sha256", "sha512"],
        }
    ).encode("utf-8")
    hasher = digest("sha256")
    hasher.update(data)
    return hasher.hexdigest()


def _from_crypto(pub: RSAPublicKey) -> SSlibKey:
    """Converts pyca/cryptography public key to SSlibKey with default signing
    scheme and legacy keyid."""
    # securesystemslib does not (yet) check if keytype and scheme are compatible
    # https://github.com/secure-systems-lab/securesystemslib/issues/766
    if not isinstance(pub, RSAPublicKey):
        raise ValueError(f"keytype '{type(pub)}' not supported")
    key = SSlibKey.from_crypto(pub, scheme="rsa-pkcs1v15-sha256")
    key.keyid = _get_legacy_keyid(key)
    return key


def load_public_key_from_file(path: Path) -> SSlibKey:
    """Load SSlibKey from RSA public key file.

    * Expected key file format is SubjectPublicKeyInfo/PEM
    * Signing scheme defaults to 'rsa-pkcs1v15-sha256'
    * Keyid is computed from legacy canonical representation of public key

    """
    with open(path, "rb") as f:
        pem = f.read()

    pub = load_pem_public_key(pem)
    return _from_crypto(pub)


def load_signer_from_file(path: Path, password: Optional[str]) -> CryptoSigner:
    """Load CryptoSigner from RSA private key file.

    * Expected key file format is PKCS8/PEM
    * Signing scheme defaults to 'rsa-pkcs1v15-sha256'
    * Keyid is computed from legacy canonical representation of public key
    * If password is None, the key is expected to be unencrypted

    """
    with open(path, "rb") as f:
        pem = f.read()

    priv = load_pem_private_key(pem, password)
    pub = priv.public_key()
    return CryptoSigner(priv, _from_crypto(pub))
