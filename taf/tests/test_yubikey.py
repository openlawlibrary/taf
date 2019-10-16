import pytest
from taf.tests import TEST_WITH_REAL_YK
from taf.yubikey import (
    DEFAULT_PIN,
    export_piv_pub_key,
    export_piv_x509,
    get_serial_num,
    is_inserted,
    sign_piv_rsa_pkcs1v15,
)


@pytest.mark.skipif(not TEST_WITH_REAL_YK, reason="list_devices() is not mocked.")
def test_is_inserted():
    assert is_inserted() is True


def test_serial_num():
    assert get_serial_num() is not None


def test_export_piv_x509():
    x509_pem = export_piv_x509()
    assert isinstance(x509_pem, bytes)


def test_export_piv_pub_key():
    pub_key_pem = export_piv_pub_key()
    assert isinstance(pub_key_pem, bytes)


def test_sign_piv_rsa_pkcs1v15(targets_yk):
    targets_yk.insert()
    # yubikey-manager only supports rsa-pkcs1v15-sha256 signature scheme
    # so skip test otherwise
    if targets_yk.scheme == "rsassa-pss-sha256":
        pytest.skip()

    from securesystemslib.pyca_crypto_keys import verify_rsa_signature

    message = b"Message to be signed."
    scheme = "rsa-pkcs1v15-sha256"

    pub_key_pem = export_piv_pub_key().decode("utf-8")
    signature = sign_piv_rsa_pkcs1v15(message, DEFAULT_PIN)

    assert verify_rsa_signature(signature, scheme, pub_key_pem, message) is True
