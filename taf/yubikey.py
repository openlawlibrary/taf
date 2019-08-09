import datetime
from contextlib import contextmanager

from cryptography.hazmat.primitives import serialization
from ykman.descriptor import list_devices, open_device
from ykman.piv import (ALGO, DEFAULT_MANAGEMENT_KEY, PIN, PIN_POLICY, PUK, SLOT,
                       PivController, generate_random_management_key)
from ykman.util import TRANSPORT


@contextmanager
def _yk():
  yk = open_device(transports=TRANSPORT.CCID)
  yield yk
  yk.close()


@contextmanager
def _yk_piv_ctrl():
  yk = open_device(transports=TRANSPORT.CCID)
  yield PivController(yk.driver)
  yk.close()


def is_inserted():
  """Checks if YubiKey is inserted.

    Args:
      None

    Returns:
      True if at least one Yubikey is inserted (bool)

    Raises:
      -
    """
  return len(list(list_devices(transports=TRANSPORT.CCID))) > 0


def get_serial_num():
  with _yk() as yk:
    return yk.serial


def export_piv_x509(cert_format=serialization.Encoding.PEM):
  """Exports YubiKey's piv slot x509.

  Args:
    - cert_format(str): One of 'serialization.Encoding' formats.

  Returns:
    PIV x509 certificate in a given format (bytes)

  Raises:
    -
  """
  with _yk_piv_ctrl() as ctrl:
    x509 = ctrl.read_certificate(SLOT.SIGNATURE)
    return x509.public_bytes(encoding=cert_format)


def export_piv_pub_key(pub_key_format=serialization.Encoding.PEM):
  """Exports YubiKey's piv slot public key.

  Args:
    - pub_key_format(str): One of 'serialization.Encoding' formats.

  Returns:
    PIV public key in a given format (bytes)

  Raises:
    -
  """
  with _yk_piv_ctrl() as ctrl:
    x509 = ctrl.read_certificate(SLOT.SIGNATURE)
    return x509.public_key().public_bytes(encoding=pub_key_format,
                                          format=serialization.PublicFormat.SubjectPublicKeyInfo)


def sign_piv_rsa_pkcs1v15(data, pin):
  """Sign data with key from YubiKey's piv slot.

  Args:
    - data(bytes): Data to be signed
    - pin(str): Pin for piv slot login.

  Returns:
    Signature (bytes)

  Raises:
    - TypeError: If data is not type of bytes.
    - ykman.piv.WrongPin: If pin is wrong.
  """
  with _yk_piv_ctrl() as ctrl:
    ctrl.verify(pin)
    return ctrl.sign(SLOT.SIGNATURE, ALGO.RSA2048, data)


def yk_setup(pin, cert_cn, cert_exp_days=365, pin_retries=10, mgm_key=generate_random_management_key()):
  """Use to setup inserted Yubikey, with following steps (order is important):
      - reset to factory settings
      - set management key
      - generate key(RSA2048)
      - generate and import self-signed certificate(X509)
      - set pin retries
      - set pin
      - set puk(same as pin)

  Args:
    - cert_cn(str): x509 common name
    - cert_exp_days(int): x509 expiration (in days from now)
    - pin_retries(int): Number of retries for PIN
    - mgm_key(bytes): New management key

  Returns:
    PIV public key in PEM format (bytes)

  Raises:
    - TypeError: If data is not type of bytes.
    - ykman.piv.WrongPin: If pin is wrong.
  """
  with _yk_piv_ctrl() as ctrl:
    # Factory reset and set PINs
    ctrl.reset()

    ctrl.authenticate(DEFAULT_MANAGEMENT_KEY)
    ctrl.set_mgm_key(mgm_key)

    # Generate RSA2048
    pub_key = ctrl.generate_key(SLOT.SIGNATURE, ALGO.RSA2048, PIN_POLICY.ALWAYS)

    ctrl.authenticate(mgm_key)
    ctrl.verify(PIN)

    # Generate and import certificate
    now = datetime.datetime.now()
    valid_to = now + datetime.timedelta(days=cert_exp_days)
    ctrl.generate_self_signed_certificate(SLOT.SIGNATURE, pub_key, cert_cn, now, valid_to)

    ctrl.set_pin_retries(pin_retries=pin_retries, puk_retries=pin_retries)
    ctrl.change_pin(PIN, pin)
    ctrl.change_puk(PUK, pin)

  return pub_key.public_bytes(
      serialization.Encoding.PEM,
      serialization.PublicFormat.SubjectPublicKeyInfo,
  )
