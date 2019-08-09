import os

import pytest

from taf.yubikey import (export_piv_pub_key, export_piv_x509, get_serial_num,
                         is_inserted, sign_piv_rsa_pkcs1v15)

# These tests should be run locally with real Yubikey
# > TEST_YK=True PIN=123456 pytest test_yubikey.py


TEST_YUBIKEY = os.environ.get('TEST_YK', False) == False
REASON = "Manually test yubikey"

PIN = os.environ.get('PIN', '')


@pytest.mark.skipif(TEST_YUBIKEY, reason=REASON)
def test_is_inserted():
  assert is_inserted() == True


@pytest.mark.skipif(TEST_YUBIKEY, reason=REASON)
def test_serial_num():
  assert get_serial_num() is not None


@pytest.mark.skipif(TEST_YUBIKEY, reason=REASON)
def test_export_piv_x509():
  x509_pem = export_piv_x509()
  assert isinstance(x509_pem, bytes)


@pytest.mark.skipif(TEST_YUBIKEY, reason=REASON)
def test_export_piv_pub_key():
  pub_key_pem = export_piv_pub_key()
  assert isinstance(pub_key_pem, bytes)


@pytest.mark.skipif(TEST_YUBIKEY, reason=REASON)
def test_sign_piv_rsa_pkcs1v15():
  from securesystemslib.pyca_crypto_keys import verify_rsa_signature

  message = b'Message to be signed.'
  scheme = 'rsa-pkcs1v15-sha256'

  pub_key_pem = export_piv_pub_key().decode('utf-8')
  signature = sign_piv_rsa_pkcs1v15(message, PIN)

  assert verify_rsa_signature(signature, scheme, pub_key_pem, message) == True
