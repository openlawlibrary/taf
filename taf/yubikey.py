import datetime
from contextlib import contextmanager
from functools import wraps

from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.serialization import load_pem_private_key
from tuf.repository_tool import import_rsakey_from_pem
from ykman.descriptor import list_devices, open_device
from ykman.piv import (ALGO, DEFAULT_MANAGEMENT_KEY, PIN_POLICY, SLOT,
                       PivController, WrongPin, generate_random_management_key)
from ykman.util import TRANSPORT

from taf.constants import DEFAULT_RSA_SIGNATURE_SCHEME
from taf.exceptions import YubikeyError

DEFAULT_PIN = '123456'
DEFAULT_PUK = '12345678'


def raise_yubikey_err(msg=None):
  """Decorator used to catch all errors raised by yubikey-manager and raise
  YubikeyError. We don't need to handle specific cases.
  """
  def wrapper(f):
    @wraps(f)
    def decorator(*args, **kwargs):
      try:
        return f(*args, **kwargs)
      except YubikeyError:
        raise
      except Exception as e:
        err_msg = '{} Reason: ({}) {}'.format(msg, type(e).__name__, str(e)) if msg else str(e)
        raise YubikeyError(err_msg) from e
    return decorator
  return wrapper


def _get_tuf_key_id_from_certificate(cert):
  """Helper function to get TAF key_id from certificate. Used if more than one
  Yubikey is inserted.
  """
  cert = cert.public_key().public_bytes(encoding=serialization.Encoding.PEM,
                                        format=serialization.PublicFormat.SubjectPublicKeyInfo)
  return import_rsakey_from_pem(cert.decode('utf-8'))['keyid']


@contextmanager
def _yk_piv_ctrl(serial=None, key_id=None):
  """Context manager to open connection and instantiate piv controller.

  Args:
    - key_id(str): TAF key_id of Yubikey to get
                   (if multiple keys are inserted)

  Returns:
    - ykman.piv.PivController

  Raises:
    - YubikeyError
  """
  # If key_id is given, iterate all devices, read x509 certs and try to match
  # key ids.
  if key_id is not None:
    for yk in list_devices(transports=TRANSPORT.CCID):
      yk_ctrl = PivController(yk.driver)
      device_key_id = _get_tuf_key_id_from_certificate(
          yk_ctrl.read_certificate(SLOT.SIGNATURE))
      if device_key_id == key_id:
        break
      else:
        yk.close()

  else:
    yk = open_device(transports=TRANSPORT.CCID, serial=serial)
    yk_ctrl = PivController(yk.driver)

  yield yk_ctrl, yk.serial
  yk.close()


def is_inserted():
  """Checks if YubiKey is inserted.

  Args:
    None

  Returns:
    True if at least one Yubikey is inserted (bool)

  Raises:
    - YubikeyError
  """
  return len(list(list_devices(transports=TRANSPORT.CCID))) > 0


@raise_yubikey_err()
def is_valid_pin(pin):
  """Checks if given pin is valid.

  Args:
    pin(str): Yubikey piv PIN

  Returns:
    tuple: True if PIN is valid, otherwise False, number of PIN retries

  Raises:
    - YubikeyError
  """
  with _yk_piv_ctrl() as (ctrl, _):
    try:
      ctrl.verify(pin)
      return True, None  # ctrl.get_pin_tries() fails if PIN is valid
    except WrongPin:
      return False, ctrl.get_pin_tries()


@raise_yubikey_err("Cannot get serial number.")
def get_serial_num(key_id=None):
  """Get Yubikey serial number.

  Args:
    None

  Returns:
    Yubikey serial number

  Raises:
    - YubikeyError
  """
  with _yk_piv_ctrl(key_id=key_id) as (_, serial):
    return serial


@raise_yubikey_err("Cannot export x509 certificate.")
def export_piv_x509(key_id=None, cert_format=serialization.Encoding.PEM):
  """Exports YubiKey's piv slot x509.

  Args:
    - cert_format(str): One of 'serialization.Encoding' formats.

  Returns:
    PIV x509 certificate in a given format (bytes)

  Raises:
    - YubikeyError
  """
  with _yk_piv_ctrl(key_id=key_id) as (ctrl, _):
    x509 = ctrl.read_certificate(SLOT.SIGNATURE)
    return x509.public_bytes(encoding=cert_format)


@raise_yubikey_err("Cannot export public key.")
def export_piv_pub_key(key_id=None, pub_key_format=serialization.Encoding.PEM):
  """Exports YubiKey's piv slot public key.

  Args:
    - pub_key_format(str): One of 'serialization.Encoding' formats.

  Returns:
    PIV public key in a given format (bytes)

  Raises:
    - YubikeyError
  """
  with _yk_piv_ctrl(key_id=key_id) as (ctrl, _):
    x509 = ctrl.read_certificate(SLOT.SIGNATURE)
    return x509.public_key().public_bytes(encoding=pub_key_format,
                                          format=serialization.PublicFormat.SubjectPublicKeyInfo)


@raise_yubikey_err("Cannot get public key in TUF format.")
def get_piv_public_key_tuf(key_id=None, scheme=DEFAULT_RSA_SIGNATURE_SCHEME):
  """Return public key from a Yubikey in TUF's RSAKEY_SCHEMA format.

  Args:
    - key_id(str): If multiple keys are inserted, get one by id
    - scheme(str): Rsa signature scheme (default is rsa-pkcs1v15-sha256)

  Returns:
    A dictionary containing the RSA keys and other identifying information
    from inserted smart card.
    Conforms to 'securesystemslib.formats.RSAKEY_SCHEMA'.

  Raises:
    - YubikeyError
  """
  pub_key_pem = export_piv_pub_key(key_id=key_id).decode('utf-8')
  return import_rsakey_from_pem(pub_key_pem, scheme)


@raise_yubikey_err("Cannot sign data.")
def sign_piv_rsa_pkcs1v15(data, pin, key_id=None):
  """Sign data with key from YubiKey's piv slot.

  Args:
    - data(bytes): Data to be signed
    - pin(str): Pin for piv slot login.

  Returns:
    Signature (bytes)

  Raises:
    - YubikeyError
  """
  with _yk_piv_ctrl(key_id=key_id) as (ctrl, _):
    ctrl.verify(pin)
    return ctrl.sign(SLOT.SIGNATURE, ALGO.RSA2048, data)


@raise_yubikey_err("Cannot setup Yubikey.")
def setup(pin, cert_cn, cert_exp_days=365, pin_retries=10,
          private_key_pem=None, mgm_key=generate_random_management_key()):
  """Use to setup inserted Yubikey, with following steps (order is important):
      - reset to factory settings
      - set management key
      - generate key(RSA2048) or import given one
      - generate and import self-signed certificate(X509)
      - set pin retries
      - set pin
      - set puk(same as pin)

  Args:
    - cert_cn(str): x509 common name
    - cert_exp_days(int): x509 expiration (in days from now)
    - pin_retries(int): Number of retries for PIN
    - private_key_pem(str): Private key in PEM format. If given, it will be
                            imported to Yubikey.
    - mgm_key(bytes): New management key

  Returns:
    PIV public key in PEM format (bytes)

  Raises:
    - YubikeyError
  """
  with _yk_piv_ctrl() as (ctrl, _):
    # Factory reset and set PINs
    ctrl.reset()

    ctrl.authenticate(DEFAULT_MANAGEMENT_KEY)
    ctrl.set_mgm_key(mgm_key)

    # Generate RSA2048
    if private_key_pem is None:
      pub_key = ctrl.generate_key(SLOT.SIGNATURE, ALGO.RSA2048, PIN_POLICY.ALWAYS)
    else:
      private_key = load_pem_private_key(private_key_pem, None, default_backend())
      ctrl.import_key(SLOT.SIGNATURE, private_key, PIN_POLICY.ALWAYS)
      pub_key = private_key.public_key()

    ctrl.authenticate(mgm_key)
    ctrl.verify(DEFAULT_PIN)

    # Generate and import certificate
    now = datetime.datetime.now()
    valid_to = now + datetime.timedelta(days=cert_exp_days)
    ctrl.generate_self_signed_certificate(SLOT.SIGNATURE, pub_key, cert_cn, now, valid_to)

    ctrl.set_pin_retries(pin_retries=pin_retries, puk_retries=pin_retries)
    ctrl.change_pin(DEFAULT_PIN, pin)
    ctrl.change_puk(DEFAULT_PUK, pin)

  return pub_key.public_bytes(
      serialization.Encoding.PEM,
      serialization.PublicFormat.SubjectPublicKeyInfo,
  )
