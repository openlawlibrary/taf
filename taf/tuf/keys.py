"""TUF metadata key functions."""

import hashlib
from typing import Callable, Dict, Optional, Tuple

from securesystemslib.signer import (
    KEY_FOR_TYPE_AND_SCHEME,
    KEY_TYPE_ECDSA,
    KEY_TYPE_ED25519,
    KEY_TYPE_MLDSA,
    KEY_TYPE_RSA,
    SSlibKey,
    CryptoSigner,
)
from securesystemslib.formats import encode_canonical
from cryptography.hazmat.primitives.serialization import (
    load_pem_private_key,
    load_pem_public_key,
)
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPublicKey
from cryptography.hazmat.primitives.asymmetric.types import PublicKeyTypes
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import serialization

from taf.exceptions import SchemeNotSpecifiedError, TAFError
from taf.utils import write_private_file

# PGP keys are left out, since they need GnuPG
SUPPORTED_KEY_TYPES = (KEY_TYPE_RSA, KEY_TYPE_ECDSA, KEY_TYPE_ED25519, KEY_TYPE_MLDSA)
# key type of each supported scheme
KEY_TYPE_OF_SCHEME = {
    scheme: keytype
    for (keytype, scheme), key_class in KEY_FOR_TYPE_AND_SCHEME.items()
    if key_class is SSlibKey and keytype in SUPPORTED_KEY_TYPES
}
SUPPORTED_SCHEMES = sorted(KEY_TYPE_OF_SCHEME)


def is_rsa_public_key(public_key_pem: str) -> bool:
    """Check if public_key_pem is the public key of an RSA key"""
    return isinstance(load_pem_public_key(public_key_pem.encode()), RSAPublicKey)


def is_rsa_scheme(scheme: Optional[str]) -> bool:
    """Check if scheme is a signing scheme of RSA keys"""
    return KEY_TYPE_OF_SCHEME.get(scheme) == KEY_TYPE_RSA


# an RSA key does not record which of these it is used with
RSA_SCHEMES = [s for s in SUPPORTED_SCHEMES if is_rsa_scheme(s)]
# schemes of the keys YubiKeys can hold
YUBIKEY_SCHEMES = sorted(
    RSA_SCHEMES + ["ecdsa-sha2-nistp256", "ecdsa-sha2-nistp384", "ed25519"]
)


def generate_keypair(
    scheme: Optional[str], rsa_key_size: Optional[int] = None
) -> Tuple[bytes, bytes]:
    """
    Generate a private and public key for the signing scheme, both in PEM
    format. The scheme sets the key type. rsa_key_size can only be set for RSA
    keys, which are 3072 bits if it is not set.
    """
    if not scheme:
        raise TAFError("A signing scheme is needed to generate a key")
    if scheme not in KEY_TYPE_OF_SCHEME:
        raise TAFError(f"Cannot generate a key for scheme '{scheme}'")
    if rsa_key_size is not None and not is_rsa_scheme(scheme):
        raise TAFError(
            f"A key size can only be set for RSA keys, not for scheme '{scheme}'"
        )
    key_generators: Dict[str, Callable[[], CryptoSigner]] = {
        KEY_TYPE_RSA: lambda: (
            CryptoSigner.generate_rsa(scheme=scheme)
            if rsa_key_size is None
            else CryptoSigner.generate_rsa(scheme=scheme, size=rsa_key_size)
        ),
        KEY_TYPE_ECDSA: lambda: CryptoSigner.generate_ecdsa(scheme=scheme),
        KEY_TYPE_ED25519: CryptoSigner.generate_ed25519,
        KEY_TYPE_MLDSA: lambda: CryptoSigner.generate_mldsa(scheme=scheme),
    }
    signer = key_generators[KEY_TYPE_OF_SCHEME[scheme]]()

    private_pem = signer.private_bytes

    # Get the public key from the private key
    public_key = load_pem_private_key(private_pem, None).public_key()
    # Serialize public key
    public_pem = public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )

    return private_pem, public_pem


def generate_and_write_keypair(
    path, scheme: Optional[str], rsa_key_size: Optional[int] = None
) -> bytes:
    """
    Generate a private and public key for the signing scheme and write them to
    path and path.pub. Returns the private key in PEM format.
    """
    private_pem, public_pem = generate_keypair(scheme, rsa_key_size)

    write_private_file(path, private_pem)

    with open(f"{path}.pub", "wb") as f:
        f.write(public_pem)

    return private_pem


def get_sslib_key_from_value(key: str, scheme: Optional[str] = None) -> SSlibKey:
    """
    Converts a key from its string representation into an SSlibKey object.
    """
    key_val = key.encode()
    crypto_key = load_pem_public_key(key_val, backend=default_backend())
    return _from_crypto(crypto_key, scheme=scheme)


def get_public_key_pem(key: SSlibKey) -> str:
    """
    Return the public key in PEM format. Ed25519 public keys are stored as hex,
    and the others as PEM.
    """
    if key.keytype != KEY_TYPE_ED25519:
        return key.keyval["public"]
    public_key = key._crypto_key()
    public_pem = public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    return public_pem.decode()


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
    return hashlib.sha256(data).hexdigest()


def _from_crypto(pub: PublicKeyTypes, scheme: Optional[str] = None) -> SSlibKey:
    """Converts pyca/cryptography public key to SSlibKey with legacy keyid.
    scheme is needed for RSA keys. The scheme of other keys is detected.
    """
    key = SSlibKey.from_crypto(pub)
    # securesystemslib does not (yet) check if keytype and scheme are compatible
    # https://github.com/secure-systems-lab/securesystemslib/issues/766
    if isinstance(pub, RSAPublicKey):
        if not scheme:
            raise SchemeNotSpecifiedError(
                "An RSA key can be used with several signing schemes "
                f"({', '.join(RSA_SCHEMES)}), so its scheme has to be specified. "
                'Set the key\'s "scheme" in the keys description, or pass --scheme '
                "to commands that take a public key file."
            )
        if not is_rsa_scheme(scheme):
            raise ValueError(f"scheme '{scheme}' not valid for rsa key")
        key = SSlibKey.from_crypto(pub, scheme=scheme)
    elif scheme not in (None, key.scheme):
        raise ValueError(f"scheme '{scheme}' not valid for {key.keytype} key")
    # FIXME: include the 'keyid_hash_algorithms' entry in the key portion
    # for legacy taf support purposes once ready to transition current authentication
    # repositories metadata over to new taf, we can safely remove the field
    key.unrecognized_fields["keyid_hash_algorithms"] = ["sha256", "sha512"]
    key.keyid = _get_legacy_keyid(key)
    return key
