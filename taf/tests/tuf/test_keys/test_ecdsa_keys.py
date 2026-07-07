import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ec import SECP256R1, SECP384R1
from cryptography.hazmat.primitives.asymmetric.ec import (
    generate_private_key as generate_ec_private_key,
)

from taf.constants import DEFAULT_ECDSA_SIGNATURE_SCHEME, DEFAULT_RSA_SIGNATURE_SCHEME
from taf.tuf.keys import get_sslib_key_from_value, load_signer_from_pem


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


def test_get_sslib_key_from_value_detects_ecdsa_with_default_rsa_scheme():
    """Callers that don't know the key type ahead of time (e.g. reading a
    YubiKey's public key) pass no explicit scheme and rely on the RSA
    default. An EC P-256 key must still be tagged correctly rather than
    silently mislabeled as RSA or rejected.
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


def test_get_sslib_key_from_value_rejects_unsupported_curve():
    _, public_pem = _ec_keypair_pem(SECP384R1())

    with pytest.raises(ValueError):
        get_sslib_key_from_value(public_pem)


def test_get_sslib_key_from_value_rejects_mismatched_scheme_for_ecdsa_key():
    _, public_pem = _ec_keypair_pem()

    with pytest.raises(ValueError):
        get_sslib_key_from_value(public_pem, "rsassa-pss-sha256")


def test_ecdsa_signer_round_trip():
    """An EC private key loaded through the same RSA-default-scheme path
    used everywhere else must produce a signer that verifies against the
    corresponding public key loaded the same way.
    """
    private_pem, public_pem = _ec_keypair_pem()

    signer = load_signer_from_pem(private_pem)
    public_key = get_sslib_key_from_value(public_pem)

    assert signer.public_key.keyid == public_key.keyid

    signature = signer.sign(b"DATA")
    public_key.verify_signature(signature, b"DATA")

    with pytest.raises(Exception):
        public_key.verify_signature(signature, b"NOT DATA")


def test_rsa_scheme_default_still_used_for_rsa_keys():
    """Regression guard: the RSA path must be entirely unaffected by the
    EC-detection branch."""
    from taf.tuf.keys import generate_rsa_keypair

    _, public_pem = generate_rsa_keypair(key_size=2048)

    key = get_sslib_key_from_value(public_pem.decode())

    assert key.keytype == "rsa"
    assert key.scheme == DEFAULT_RSA_SIGNATURE_SCHEME
