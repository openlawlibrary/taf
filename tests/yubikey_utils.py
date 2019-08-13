import datetime
import random
from contextlib import contextmanager

from cryptography import x509
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes, serialization

from securesystemslib.pyca_crypto_keys import create_rsa_signature
from tuf.repository_tool import import_rsakey_from_pem

INSERTED_YUBIKEY = None


class FakeYubiKey:
  def __init__(self, priv_key_path, pub_key_path, serial=None):
    self.priv_key_pem = priv_key_path.read_bytes()
    self.pub_key_pem = pub_key_path.read_bytes()

    self._serial = serial if serial else random.randint(100000, 999999)

  @property
  def driver(self):
    return self

  @property
  def serial(self):
    return self._serial

  def insert(self):
    """Insert YubiKey in USB slot."""
    global INSERTED_YUBIKEY
    INSERTED_YUBIKEY = self

  def is_inserted(self):
    """Check if YubiKey is in USB slot."""
    global INSERTED_YUBIKEY
    return INSERTED_YUBIKEY is self

  def remove(self):
    """Removes YubiKey from USB slot."""
    global INSERTED_YUBIKEY
    if INSERTED_YUBIKEY is self:
      INSERTED_YUBIKEY = None


class FakePivController:
  def __init__(self, driver):
    self._driver = driver

    self.priv_key = serialization.load_pem_private_key(
        self._driver.priv_key_pem, None, default_backend())
    self.pub_key = serialization.load_pem_public_key(
        self._driver.pub_key_pem, default_backend())

    self._tuf_key = import_rsakey_from_pem(self._driver.priv_key_pem.decode('utf-8'))

  @property
  def driver(self):
    return None

  def authenticate(self, *args, **kwargs):
    pass

  def change_pin(self, *args, **kwargs):
    pass

  def change_puk(self, *args, **kwargs):
    pass

  def generate_self_signed_certificate(self, *args, **kwargs):
    pass

  def read_certificate(self, _slot):
    name = x509.Name([
        x509.NameAttribute(x509.NameOID.COMMON_NAME, self.__class__.__name__)
    ])
    now = datetime.datetime.utcnow()

    return (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(self.pub_key)
        .serial_number(self._driver.serial)
        .not_valid_before(now)
        .not_valid_after(now + datetime.timedelta(days=365))
        .sign(self.priv_key, hashes.SHA256(), default_backend())
    )

  def reset(self):
    pass

  def set_pin_retries(self, *args, **kwargs):
    pass

  def sign(self, slot, algorithm, data):
    """Sign data using the same function as TUF"""
    # TODO: Revisit - Should data be passed as bytes already?
    if isinstance(data, str):
      data = data.encode('utf-8')

    private_key = self._tuf_key['keyval']['private']
    sig, _ = create_rsa_signature(private_key, data, 'rsassa-pss-sha256')
    return sig

  def verify(self, *args, **kwargs):
    pass


class TargetYubiKey(FakeYubiKey):
  def __init__(self, keystore_path):
    super().__init__(keystore_path / 'targets', keystore_path / 'targets.pub')


class Root1YubiKey(FakeYubiKey):
  def __init__(self, keystore_path):
    super().__init__(keystore_path / 'root1', keystore_path / 'root1.pub')


class Root2YubiKey(FakeYubiKey):
  def __init__(self, keystore_path):
    super().__init__(keystore_path / 'root2', keystore_path / 'root2.pub')


class Root3YubiKey(FakeYubiKey):
  def __init__(self, keystore_path):
    super().__init__(keystore_path / 'root3', keystore_path / 'root3.pub')


@contextmanager
def _yk_piv_ctrl_mock(serial=None, key_id=None):
  global INSERTED_YUBIKEY
  yield FakePivController(INSERTED_YUBIKEY), INSERTED_YUBIKEY.serial
