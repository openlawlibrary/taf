from functools import wraps

from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import serialization
from PyKCS11 import (CKO_CERTIFICATE, CKO_PRIVATE_KEY, CKO_PUBLIC_KEY,
                     PyKCS11Error)


class _Session:
  """Fake pkcs11 session implementation used to test API.
  For more info:
    https://github.com/LudovicRousseau/PyKCS11/blob/master/PyKCS11/__init__.py#L851
  """

  def __init__(self, yubikey):
    self.yubikey = yubikey

  def closeSession(self):
    pass

  def findObjects(self, *args):
    return {
        CKO_CERTIFICATE: ['cert'],
        CKO_PUBLIC_KEY: ['pub_key'],
        CKO_PRIVATE_KEY: ['priv_key']
    }.get(args[0][1][1], [])

  def getAttributeValue(self, obj, *args):
    return {
        'cert': ['TODO: Create certificates'],
        'pub_key': [self.yubikey.pub_key_der]
    }.get(obj, [])

  def login(self, pin, user_type=None):
    if pin != self.yubikey.pin:
      raise PyKCS11Error('Could not login.')

  def logout(self):
    pass

  def sign(self, pk, data, mechanism):
    return b'signature'


class PKCS11:
  """Fake pkcs11 lib implementation used to test API.
  For more info:
    https://github.com/LudovicRousseau/PyKCS11/blob/master/PyKCS11/__init__.py#L453
  """

  def __init__(self, yubikey):
    self.yubikey = yubikey

  def getSlotList(self, tokenPresent=False):
    if self.yubikey and self.yubikey.is_inserted():
      return [0]
    else:
      return []

  def openSession(self, slot, flags=0):
    return _Session(self.yubikey)


INSERTED_YUBIKEY = None


def init_pkcs11_mock(api_func):
  @wraps(api_func)
  def decorator(*args, **kwargs):
    pkcs11 = kwargs.pop('pkcs11', None)
    if pkcs11 is None:
      global INSERTED_YUBIKEY
      pkcs11 = PKCS11(INSERTED_YUBIKEY)
    kwargs['pkcs11'] = pkcs11
    return api_func(*args, **kwargs)
  return decorator


class FakeYubiKey:
  def __init__(self, priv_key_path, pub_key_path, pin='123456'):
    self.priv_key = priv_key_path.read_bytes()
    self.pub_key_pem = pub_key_path.read_bytes()

    rsa_pub_pem = serialization.load_pem_public_key(self.pub_key_pem, default_backend())
    self.pub_key_der = rsa_pub_pem.public_bytes(
        serialization.Encoding.DER,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    )

    self.pin = pin

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

  def sign(self, data):
    """TODO: Sign data using the same function as TUF"""


class TargetYubiKey(FakeYubiKey):
  def __init__(self, keystore_path):
    super().__init__(keystore_path / 'targets', keystore_path / 'targets.pub')


class Root1YubiKey(FakeYubiKey):
  def __init__(self, keystore_path):
    super().__init__(keystore_path / 'root_key1', keystore_path / 'root_key1.pub')


class Root2YubiKey(FakeYubiKey):
  def __init__(self, keystore_path):
    super().__init__(keystore_path / 'root_key2', keystore_path / 'root_key2.pub')


class Root3YubiKey(FakeYubiKey):
  def __init__(self, keystore_path):
    super().__init__(keystore_path / 'root_key3', keystore_path / 'root_key3.pub')
