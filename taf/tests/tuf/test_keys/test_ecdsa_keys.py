import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ec import SECP256R1, SECP384R1
from cryptography.hazmat.primitives.asymmetric.ec import (
    generate_private_key as generate_ec_private_key,
)

from taf.constants import DEFAULT_ECDSA_SIGNATURE_SCHEME, DEFAULT_RSA_SIGNATURE_SCHEME
from taf.exceptions import SchemeNotSpecifiedError
from taf.tuf.signer_uris import import_keystore_signer
from taf.tuf.keys import (
    generate_keypair,
    get_sslib_key_from_value,
)


def _ec_keypair_pem(curve=SECP256R1()):
    private_key = generate_ec_private_key(curve)
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    public_pem = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    return private_pem, public_pem.decode()


def test_get_sslib_key_from_value_detects_ecdsa_scheme():
    """Callers that don't know the key type ahead of time (e.g. reading a
    YubiKey's public key) pass no explicit scheme. An EC P-256 key has only
    one scheme, so it must be detected rather than rejected.
    """
    _, public_pem = _ec_keypair_pem()

    key = get_sslib_key_from_value(public_pem)

    assert key.keytype == "ecdsa"
    assert key.scheme == DEFAULT_ECDSA_SIGNATURE_SCHEME


def test_get_sslib_key_from_value_accepts_explicit_ecdsa_scheme():
    _, public_pem = _ec_keypair_pem()

    key = get_sslib_key_from_value(public_pem, DEFAULT_ECDSA_SIGNATURE_SCHEME)

    assert key.keytype == "ecdsa"
    assert key.scheme == DEFAULT_ECDSA_SIGNATURE_SCHEME


def test_get_sslib_key_from_value_detects_ecdsa_curve():
    _, public_pem = _ec_keypair_pem(SECP384R1())

    key = get_sslib_key_from_value(public_pem)

    assert key.keytype == "ecdsa"
    assert key.scheme == "ecdsa-sha2-nistp384"


def test_get_sslib_key_from_value_rejects_mismatched_scheme_for_ecdsa_key():
    _, public_pem = _ec_keypair_pem()

    with pytest.raises(ValueError):
        get_sslib_key_from_value(public_pem, "rsassa-pss-sha256")


def test_ecdsa_signer_round_trip(keystore_of_scheme):
    """An EC keystore file loaded through its URI must produce a signer that
    verifies against the corresponding public key.
    """
    keystore = keystore_of_scheme(DEFAULT_ECDSA_SIGNATURE_SCHEME)

    signer = import_keystore_signer(keystore, "targets")
    public_key = get_sslib_key_from_value((keystore / "targets.pub").read_text())

    assert signer.public_key.keyid == public_key.keyid

    signature = signer.sign(b"DATA")
    public_key.verify_signature(signature, b"DATA")

    with pytest.raises(Exception):
        public_key.verify_signature(signature, b"NOT DATA")


def test_rsa_key_without_scheme_is_rejected():
    _, public_pem = generate_keypair("rsa-pkcs1v15-sha256", 2048)

    with pytest.raises(SchemeNotSpecifiedError):
        get_sslib_key_from_value(public_pem.decode())

    key = get_sslib_key_from_value(public_pem.decode(), DEFAULT_RSA_SIGNATURE_SCHEME)
    assert key.scheme == DEFAULT_RSA_SIGNATURE_SCHEME
