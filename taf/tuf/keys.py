"""TUF metadata key functions."""

import hashlib
import os
from typing import Callable, Dict, Optional, Tuple
from urllib import parse

from securesystemslib.signer import (
    KEY_FOR_TYPE_AND_SCHEME,
    KEY_TYPE_ECDSA,
    KEY_TYPE_ED25519,
    KEY_TYPE_MLDSA,
    KEY_TYPE_RSA,
    SIGNER_FOR_URI_SCHEME,
    SSlibKey,
    CryptoSigner,
    Signer,
    SecretsHandler,
    Signature,
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


def _generate_rsa_key(scheme: str, rsa_key_size: Optional[int]) -> CryptoSigner:
    if rsa_key_size is None:
        return CryptoSigner.generate_rsa(scheme=scheme)
    return CryptoSigner.generate_rsa(scheme=scheme, size=rsa_key_size)


# how to generate a key of each supported key type, given its scheme and RSA
# key size. PGP keys are left out, since they need GnuPG
KEY_GENERATORS: Dict[str, Callable[[str, Optional[int]], CryptoSigner]] = {
    KEY_TYPE_RSA: _generate_rsa_key,
    KEY_TYPE_ECDSA: lambda scheme, _rsa_key_size: CryptoSigner.generate_ecdsa(
        scheme=scheme
    ),
    KEY_TYPE_ED25519: lambda _scheme, _rsa_key_size: CryptoSigner.generate_ed25519(),
    KEY_TYPE_MLDSA: lambda scheme, _rsa_key_size: CryptoSigner.generate_mldsa(
        scheme=scheme
    ),
}
# key type of each supported scheme
KEY_TYPE_OF_SCHEME = {
    scheme: keytype
    for (keytype, scheme), key_class in KEY_FOR_TYPE_AND_SCHEME.items()
    if key_class is SSlibKey and keytype in KEY_GENERATORS
}
SUPPORTED_SCHEMES = sorted(KEY_TYPE_OF_SCHEME)


def is_rsa_scheme(scheme: Optional[str]) -> bool:
    """Check if scheme is a signing scheme of RSA keys"""
    return KEY_TYPE_OF_SCHEME.get(scheme) == KEY_TYPE_RSA


# YubiKeys can't hold P-521 or ML-DSA keys
YUBIKEY_SCHEMES = [
    s
    for s in SUPPORTED_SCHEMES
    if s != "ecdsa-sha2-nistp521" and KEY_TYPE_OF_SCHEME[s] != KEY_TYPE_MLDSA
]
# an RSA key does not record which of these it is used with
RSA_SCHEMES = [s for s in SUPPORTED_SCHEMES if is_rsa_scheme(s)]


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
    signer = KEY_GENERATORS[KEY_TYPE_OF_SCHEME[scheme]](scheme, rsa_key_size)

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

    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC | getattr(os, "O_BINARY", 0)
    with os.fdopen(os.open(path, flags, 0o600), "wb") as f:
        f.write(private_pem)
    os.chmod(path, 0o600)

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
    Return the public key in PEM format.
    """
    if key.keyval["public"].startswith("-----BEGIN"):
        return key.keyval["public"]
    public_key = key._crypto_key()
    public_pem = public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    return public_pem.decode()


def is_same_public_key(key: SSlibKey, public_key_pem: str) -> bool:
    """Check if key's public key is the one in public_key_pem, whatever their
    signing schemes"""
    public_key = load_pem_public_key(public_key_pem.encode())
    der_format = (
        serialization.Encoding.DER,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    try:
        key_der = key._crypto_key().public_bytes(*der_format)
    except Exception:
        return False
    return key_der == public_key.public_bytes(*der_format)


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


class YkSigner(Signer):
    """Signer implementation for Yubikeys.

    Provides a minimal compatibility layer over `taf.yubikey` module functions
    for use with MetadataRepository.

    Attrs:
        public_key: An SSlibkey, whose keyid and signing scheme are the single
                of truth for creating signatures.
        pin_handler: A function, which is called in `sign` and expected to
                return the Yubikey pin.
    """

    SCHEME = "yk"
    _SECRET_PROMPT = "pin"  # nosec B105

    def __init__(
        self,
        public_key: SSlibKey,
        serial_num: int,
        pin_handler: SecretsHandler,
        key_name: str,
        slot=None,
    ):

        self._public_key = public_key
        self._pin_handler = pin_handler
        self._serial_num = serial_num
        self._key_name = key_name
        # the PIV slot holding this key; None defaults to SLOT.SIGNATURE in
        # sign() - kept untyped here so this module stays importable without
        # yubikey-manager installed (an optional extra)
        self._slot = slot
        from taf.yubikey.yubikey import get_piv_sign_args

        self._sign_args = get_piv_sign_args(public_key)

    @property
    def public_key(self) -> SSlibKey:
        return self._public_key

    @property
    def serial_num(self) -> int:
        return self._serial_num

    @property
    def key_name(self) -> str:
        return self._key_name

    @property
    def slot(self):
        return self._slot

    def sign(self, payload: bytes) -> Signature:
        pin = self._pin_handler(self._SECRET_PROMPT)
        from taf.yubikey.yubikey import sign_piv, verify_yk_inserted
        from yubikit.piv import SLOT

        verify_yk_inserted(self.serial_num, self.key_name)
        slot = self._slot if self._slot is not None else SLOT.SIGNATURE
        sig = sign_piv(payload, pin, self._sign_args, serial=self.serial_num, slot=slot)
        return Signature(self.public_key.keyid, sig.hex())

    @classmethod
    def from_priv_key_uri(
        cls,
        priv_key_uri: str,
        public_key: SSlibKey,
        secrets_handler: Optional[SecretsHandler] = None,
    ) -> "Signer":
        """URI format: ``yk:<serial>?slot=<hex PIV slot>&name=<key name>``.
        Slot and name are optional."""
        uri = parse.urlparse(priv_key_uri)
        if uri.scheme != cls.SCHEME:
            raise ValueError(f"YkSigner does not support {priv_key_uri}")
        if secrets_handler is None:
            raise ValueError("YkSigner requires a secrets handler for the PIN")
        params = dict(parse.parse_qsl(uri.query))
        slot = None
        if "slot" in params:
            from yubikit.piv import SLOT

            slot = SLOT(int(params["slot"], 16))
        serial_num = int(uri.path)
        return cls(
            public_key,
            serial_num,
            secrets_handler,
            key_name=params.get("name", str(serial_num)),
            slot=slot,
        )


SIGNER_FOR_URI_SCHEME[YkSigner.SCHEME] = YkSigner
