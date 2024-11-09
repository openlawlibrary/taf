"""TUF metadata key functions.

"""


from typing import Optional

from pathlib import Path
from securesystemslib.signer import (
    SSlibKey,
    CryptoSigner,
    Signer,
    SecretsHandler,
    Signature,
)
from securesystemslib.formats import encode_canonical
from securesystemslib.hash import digest
from cryptography.hazmat.primitives.serialization import (
    load_pem_private_key,
    load_pem_public_key,
)
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPublicKey
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from taf import YubikeyMissingLibrary
from taf.constants import DEFAULT_RSA_SIGNATURE_SCHEME


try:
    import taf.yubikey as yk
except ImportError:
    yk = YubikeyMissingLibrary()  # type: ignore


def create_signer(priv, pub):
    return CryptoSigner(priv, _from_crypto(pub))


def generate_rsa_keypair(key_size=3072, password=None):
    # Generate private key
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=key_size,
        backend=default_backend()
    )

    # Encrypt the private key if a password is provided
    if password:
        encryption_algorithm = serialization.BestAvailableEncryption(password.encode())
    else:
        encryption_algorithm = serialization.NoEncryption()

    # Serialize private key
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=encryption_algorithm
    )

    # Get the public key from the private key
    public_key = private_key.public_key()
    # Serialize public key
    public_pem = public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo
    )

    return private_pem, public_pem

def generate_and_write_rsa_keypair(path, key_size, password):

    if not password:
        password = None
    private_pem, public_pem = generate_rsa_keypair(key_size, password)

    with open(path, "wb") as f:
        f.write(private_pem)

    with open(f"{path}.pub", 'wb') as f:
        f.write(public_pem)

    return private_pem


def _get_key_name(role_name: str, key_num: int, num_of_keys: int) -> str:
    """
    Return a keystore key's name based on the role's name and total number of signing keys,
    as well as the specified counter. If number of signing keys is one, return the role's name.
    If the number of signing keys is greater that one, return role's name + counter (root1, root2...)
    """
    if num_of_keys == 1:
        return role_name
    else:
        return role_name + str(key_num + 1)


def get_sslib_key_from_value(key: str, scheme:str=DEFAULT_RSA_SIGNATURE_SCHEME) -> SSlibKey:
    key_val = key.encode()
    crypto_key = load_pem_public_key(key_val, backend=default_backend())
    return SSlibKey.from_crypto(crypto_key, scheme=scheme)


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



def load_public_key_from_file(path: Path, scheme=DEFAULT_RSA_SIGNATURE_SCHEME) -> SSlibKey:
    """Load SSlibKey from RSA public key file.

    * Expected key file format is SubjectPublicKeyInfo/PEM
    * Signing scheme defaults to 'rsa-pkcs1v15-sha256'
    * Keyid is computed from legacy canonical representation of public key

    """
    # TODO handle scheme
    with open(path, "rb") as f:
        pem = f.read()

    pub = load_pem_public_key(pem)
    return _from_crypto(pub)


def load_signer_from_file(path: Path, password: Optional[str]=None, scheme=DEFAULT_RSA_SIGNATURE_SCHEME) -> CryptoSigner:
    """Load CryptoSigner from RSA private key file.

    * Expected key file format is PKCS8/PEM
    * Signing scheme defaults to 'rsa-pkcs1v15-sha256'
    * Keyid is computed from legacy canonical representation of public key
    * If password is None, the key is expected to be unencrypted

    """
    with open(path, "rb") as f:
        pem = f.read()

    # TODO scheme

    password_encoded = password.encode() if password is not None else None
    priv = load_pem_private_key(pem, password_encoded)
    pub = priv.public_key()
    return CryptoSigner(priv, _from_crypto(pub))


def load_signer_from_pem(pem: bytes, password: Optional[bytes]=None) -> CryptoSigner:
    """Load CryptoSigner from RSA private key file.

    * Expected key file format is PKCS8/PEM
    * Signing scheme defaults to 'rsa-pkcs1v15-sha256'
    * Keyid is computed from legacy canonical representation of public key
    * If password is None, the key is expected to be unencrypted

    """
    priv = load_pem_private_key(pem, password)
    pub = priv.public_key()
    return CryptoSigner(priv, _from_crypto(pub))


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

    _SECRET_PROMPT = "pin"

    def __init__(self, public_key: SSlibKey, pin_handler: SecretsHandler):

        self._public_key = public_key
        self._pin_handler = pin_handler

    @property
    def public_key(self) -> SSlibKey:
        return self._public_key

    @classmethod
    def import_(cls) -> SSlibKey:
        """Import rsa public key from Yubikey.

        * Assigns default signing scheme: "rsa-pkcs1v15-sha256"
        * Raises ValueError, if key on Yubikey is not an rsa key.

        TODO: Consider returning priv key uri along with public key.
        See e.g. `self.from_priv_key_uri` and other `import_` methods on
        securesystemslib signers, e.g. `HSMSigner.import_`.
        """
        # TODO: export pyca/cryptography key to avoid duplicate deserialization
        pem = yk.export_piv_pub_key()
        pub = load_pem_public_key(pem)
        return _from_crypto(pub)

    def sign(self, payload: bytes) -> Signature:
        pin = self._pin_handler(self._SECRET_PROMPT)
        # TODO: openlawlibrary/taf#515
        # sig = sign_piv_rsa_pkcs1v15(payload, pin, self.public_key.keyval["public"])
        sig = yk.sign_piv_rsa_pkcs1v15(payload, pin)
        return Signature(self.public_key.keyid, sig.hex())

    @classmethod
    def from_priv_key_uri(
        cls,
        priv_key_uri: str,
        public_key: SSlibKey,
        secrets_handler: Optional[SecretsHandler] = None,
    ) -> "Signer":
        # TODO: Implement this to better separate public key management
        # (e.g. tuf delegation) and signer configuration from signing. See
        # https://python-securesystemslib.readthedocs.io/en/latest/signer.html
        raise NotImplementedError


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


def yubikey_signature_provider(name, key_id, key, data):  # pylint: disable=W0613
    """
    A signatures provider which asks the user to insert a yubikey
    Useful if several yubikeys need to be used at the same time
    """
    from binascii import hexlify

    def _check_key_and_get_pin(expected_key_id):
        try:
            inserted_key = yk.get_piv_public_key_tuf()
            if expected_key_id != inserted_key["keyid"]:
                return None
            serial_num = yk.get_serial_num(inserted_key)
            pin = yk.get_key_pin(serial_num)
            if pin is None:
                pin = yk.get_and_validate_pin(name)
            return pin
        except Exception:
            return None

    while True:
        # check if the needed YubiKey is inserted before asking the user to do so
        # this allows us to use this signature provider inside an automated process
        # assuming that all YubiKeys needed for signing are inserted
        pin = _check_key_and_get_pin(key_id)
        if pin is not None:
            break
        input(f"\nInsert {name} and press enter")

    signature = yk.sign_piv_rsa_pkcs1v15(data, pin)
    return {"keyid": key_id, "sig": hexlify(signature).decode()}
