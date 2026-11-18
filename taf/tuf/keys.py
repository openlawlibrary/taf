"""TUF metadata key functions."""

import hashlib
import os
from typing import Optional, Tuple, Union
from urllib import parse

from pathlib import Path
from securesystemslib.signer import (
    KEY_FOR_TYPE_AND_SCHEME,
    KEY_TYPE_ECDSA,
    KEY_TYPE_ED25519,
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
from cryptography.hazmat.primitives.asymmetric.types import PublicKeyTypes
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import serialization

from taf.constants import DEFAULT_RSA_SIGNATURE_SCHEME


def generate_keypair(scheme: str, rsa_key_size: int = 3072) -> Tuple[bytes, bytes]:
    """
    Generate a private and public key for the signing scheme, both in PEM
    format. securesystemslib generates the key and the scheme decides its
    type. rsa_key_size is only used for RSA keys.
    """
    if not scheme:
        raise ValueError("A signing scheme is needed to generate a key")
    keytypes = {
        keytype
        for (keytype, key_scheme), key_class in KEY_FOR_TYPE_AND_SCHEME.items()
        if key_scheme == scheme and key_class is SSlibKey
    }
    signer: CryptoSigner
    if KEY_TYPE_RSA in keytypes:
        signer = CryptoSigner.generate_rsa(scheme=scheme, size=rsa_key_size)
    elif KEY_TYPE_ECDSA in keytypes:
        signer = CryptoSigner.generate_ecdsa(scheme=scheme)
    elif KEY_TYPE_ED25519 in keytypes:
        signer = CryptoSigner.generate_ed25519()
    else:
        raise ValueError(f"cannot generate a key for scheme '{scheme}'")

    private_pem = signer.private_bytes
    public_pem = (
        load_pem_private_key(private_pem, None)
        .public_key()
        .public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
    )
    return private_pem, public_pem


def generate_and_write_keypair(path, scheme: str, rsa_key_size: int = 3072) -> bytes:
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


def get_rsa_key_size(key: SSlibKey) -> Optional[int]:
    """Return the size of an RSA key in bits, or None for other key types"""
    if key.keytype != KEY_TYPE_RSA:
        return None
    return load_pem_public_key(key.keyval["public"].encode()).key_size  # type: ignore


def get_sslib_key_from_value(key: str, scheme: Optional[str] = None) -> SSlibKey:
    """
    Converts a key from its string representation into an SSlibKey object.
    """
    key_val = key.encode()
    crypto_key = load_pem_public_key(key_val, backend=default_backend())
    return _from_crypto(crypto_key, scheme=scheme)


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

    securesystemslib detects the key type and its default scheme. RSA keys can
    use several schemes and default to rsa-pkcs1v15-sha256, so that keyids of
    existing RSA keys stay the same. Other key types have only one scheme.
    """
    key = SSlibKey.from_crypto(pub)
    # securesystemslib does not check if keytype and scheme are compatible
    if key.keytype == KEY_TYPE_RSA:
        scheme = scheme or DEFAULT_RSA_SIGNATURE_SCHEME
        rsa_schemes = {
            rsa_scheme
            for (keytype, rsa_scheme), key_class in KEY_FOR_TYPE_AND_SCHEME.items()
            if keytype == KEY_TYPE_RSA and key_class is SSlibKey
        }
        if scheme not in rsa_schemes:
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


def load_public_key_from_file(path: Union[str, Path]) -> SSlibKey:
    """Load SSlibKey from a public key file.

    * Expected key file format is SubjectPublicKeyInfo/PEM
    * Signing scheme is detected from the key material (RSA or ECDSA P-256)
    * Keyid is computed from legacy canonical representation of public key

    """
    with open(path, "rb") as f:
        pem = f.read()

    pub = load_pem_public_key(pem)
    return _from_crypto(pub)


def load_signer_from_file(path: Path) -> CryptoSigner:
    """Load CryptoSigner from a private key file.

    * Expected key file format is PKCS8/PEM
    * Signing scheme is detected from the key material (RSA or ECDSA P-256)
    * Keyid is computed from legacy canonical representation of public key
    * The key is expected to be unencrypted

    """
    with open(path, "rb") as f:
        pem = f.read()

    priv = load_pem_private_key(pem, None)
    pub = priv.public_key()
    return CryptoSigner(priv, _from_crypto(pub))


def load_signer_from_pem(pem: bytes, scheme: Optional[str] = None) -> CryptoSigner:
    """Load CryptoSigner from a private key in PEM format.

    * Expected key file format is PKCS8/PEM
    * Signing scheme is detected from the key material (RSA or ECDSA P-256)
      unless explicitly overridden, which only makes sense for RSA, where
      the sub-scheme (e.g. rsassa-pss-sha256) can't be inferred from the
      key bytes alone
    * Keyid is computed from legacy canonical representation of public key
    * The key is expected to be unencrypted

    """
    priv = load_pem_private_key(pem, None)
    pub = priv.public_key()
    return CryptoSigner(priv, _from_crypto(pub, scheme))


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

    @classmethod
    def import_(cls) -> SSlibKey:
        """Import rsa public key from Yubikey.

        * Assigns default signing scheme: "rsa-pkcs1v15-sha256"
        * Raises ValueError, if key on Yubikey is not an rsa key.

        TODO: Consider returning priv key uri along with public key.
        See e.g. `self.from_priv_key_uri` and other `import_` methods on
        securesystemslib signers, e.g. `HSMSigner.import_`.

        TODO: only checks SLOT.SIGNATURE, same as export_piv_pub_key -
        test-only helper per the comment below, so not extended to other
        slots for now.
        """
        # if multiple keys are inserted, we need to know from which key should be imported
        # TODO
        # only used for testing purposes now
        from taf.yubikey.yubikey import export_piv_pub_key, get_serial_nums

        serials = get_serial_nums()
        serial = serials[0]
        pem = export_piv_pub_key(serial=serial)
        pub = load_pem_public_key(pem)
        return _from_crypto(pub)

    def sign(self, payload: bytes) -> Signature:
        pin = self._pin_handler(self._SECRET_PROMPT)
        from taf.yubikey.yubikey import sign_piv_rsa_pkcs1v15, verify_yk_inserted
        from yubikit.piv import SLOT

        verify_yk_inserted(self.serial_num, self.key_name)
        slot = self._slot if self._slot is not None else SLOT.SIGNATURE
        sig = sign_piv_rsa_pkcs1v15(payload, pin, serial=self.serial_num, slot=slot)
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


def root_signature_provider(signature_dict, key_id, _key, _data):
    """Root signature provider used to return signatures created remotely.

    Args:
        - signature_dict(dict): Dict where key is key_id and value is signature
        - key_id(str): Key id from targets metadata file
        - _key(securesystemslib.formats.RSAKEY_SCHEMA): Key info
        - _data(dict): Data to sign (already signed remotely)

    Returns:
        Dictionary that comforms to `securesystemslib.formats.SIGNATURE_SCHEMA`

    Raises:
        - KeyError: If signature for key_id is not present in signature_dict
    """
    from binascii import hexlify

    return {"keyid": key_id, "sig": hexlify(signature_dict.get(key_id)).decode()}
