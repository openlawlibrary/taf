import datetime
import random
from contextlib import contextmanager

from cryptography import x509
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes, serialization
from securesystemslib.pyca_crypto_keys import create_rsa_signature
from tuf.repository_tool import import_rsakey_from_pem
from ykman.descriptor import FailedOpeningDeviceException
from ykman.piv import WrongPin

VALID_PIN = "123456"
WRONG_PIN = "111111"

INSERTED_YUBIKEY = None


class FakeYubiKey:
    def __init__(self, priv_key_path, pub_key_path, scheme, serial=None, pin=VALID_PIN):
        self.priv_key_pem = priv_key_path.read_bytes()
        self.pub_key_pem = pub_key_path.read_bytes()

        self._serial = serial if serial else random.randint(100000, 999999)
        self._pin = pin

        self.scheme = scheme
        self.priv_key = serialization.load_pem_private_key(
            self.priv_key_pem, None, default_backend()
        )
        self.pub_key = serialization.load_pem_public_key(
            self.pub_key_pem, default_backend()
        )

        self.tuf_key = import_rsakey_from_pem(self.pub_key_pem.decode("utf-8"), scheme)

    @property
    def driver(self):
        return self

    @property
    def pin(self):
        return self._pin

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
        name = x509.Name(
            [x509.NameAttribute(x509.NameOID.COMMON_NAME, self.__class__.__name__)]
        )
        now = datetime.datetime.utcnow()

        return (
            x509.CertificateBuilder()
            .subject_name(name)
            .issuer_name(name)
            .public_key(self._driver.pub_key)
            .serial_number(self._driver.serial)
            .not_valid_before(now)
            .not_valid_after(now + datetime.timedelta(days=365))
            .sign(self._driver.priv_key, hashes.SHA256(), default_backend())
        )

    def reset(self):
        pass

    def set_pin_retries(self, *args, **kwargs):
        pass

    def sign(self, slot, algorithm, data):
        """Sign data using the same function as TUF"""
        if isinstance(data, str):
            data = data.encode("utf-8")

        sig, _ = create_rsa_signature(
            self._driver.priv_key_pem.decode("utf-8"), data, self._driver.scheme
        )
        return sig

    def verify(self, pin):
        if self._driver.pin != pin:
            raise WrongPin("", "")


class TargetYubiKey(FakeYubiKey):
    def __init__(self, keystore_path, scheme):
        super().__init__(
            keystore_path / "targets", keystore_path / "targets.pub", scheme
        )


class Root1YubiKey(FakeYubiKey):
    def __init__(self, keystore_path, scheme):
        super().__init__(keystore_path / "root1", keystore_path / "root1.pub", scheme)


class Root2YubiKey(FakeYubiKey):
    def __init__(self, keystore_path, scheme):
        super().__init__(keystore_path / "root2", keystore_path / "root2.pub", scheme)


class Root3YubiKey(FakeYubiKey):
    def __init__(self, keystore_path, scheme):
        super().__init__(keystore_path / "root3", keystore_path / "root3.pub", scheme)


@contextmanager
def _yk_piv_ctrl_mock(serial=None, pub_key_pem=None):
    global INSERTED_YUBIKEY

    if INSERTED_YUBIKEY is None:
        raise FailedOpeningDeviceException()

    yield FakePivController(INSERTED_YUBIKEY), INSERTED_YUBIKEY.serial
