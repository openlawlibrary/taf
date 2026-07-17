import datetime
import secrets
from contextlib import contextmanager

from cryptography import x509
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes, serialization
from taf.tuf.keys import load_signer_from_file
from ykman.piv import OBJECT_ID_PIVMAN_PROTECTED_DATA
from yubikit.core.smartcard import ApduError, SW
from yubikit.piv import DEFAULT_MANAGEMENT_KEY, SLOT, InvalidPinError

VALID_PIN = "123456"
WRONG_PIN = "111111"

INSERTED_YUBIKEY = None


class FakeYubiKey:
    def __init__(self, priv_key_path, pub_key_path, scheme, serial=None, pin=VALID_PIN):
        self.priv_key_pem = priv_key_path.read_bytes()
        self.pub_key_pem = pub_key_path.read_bytes()

        self._serial = serial if serial else secrets.randbelow(900000) + 100000
        self._pin = pin

        self.scheme = scheme
        self.priv_key = serialization.load_pem_private_key(
            self.priv_key_pem, None, default_backend()
        )
        self.pub_key = serialization.load_pem_public_key(
            self.pub_key_pem, default_backend()
        )

        self.tuf_key = load_signer_from_file(priv_key_path)

        # PIV slot state (key/cert per slot), persisted here rather than on
        # FakePivController, since a new FakePivController is constructed on
        # every `with _yk_piv_ctrl(...)` block - this is what needs to
        # survive across separate calls (e.g. setup() then get_slot_status())
        self.slots: dict = {}
        # PIV general data objects (object ID -> raw bytes), used to model
        # the PIN-protected management key storage (see get_object/put_object)
        self.data_objects: dict = {}
        self.pin_verified = False
        self.management_key = DEFAULT_MANAGEMENT_KEY

    @property
    def driver(self):
        return self

    @property
    def pin(self):
        return self._pin

    @pin.setter
    def pin(self, value):
        self._pin = value

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
    """Fake yubikit.piv.PivSession, standing in for a real PIV connection in
    tests: PIN/management-key authentication, signing, and per-slot
    key/certificate storage. SLOT.SIGNATURE starts out "occupied" with the
    driver's own key/cert, matching a YubiKey that's already been set up
    the traditional way; every other slot starts free.
    """

    def __init__(self, driver):
        self._driver = driver
        # slot state lives on the driver (FakeYubiKey), not here, so it
        # survives across separate `with _yk_piv_ctrl(...)` blocks
        if SLOT.SIGNATURE not in driver.slots:
            driver.slots[SLOT.SIGNATURE] = {
                "priv_key": driver.priv_key,
                "pub_key": driver.pub_key,
                "cert": self._build_certificate(driver.pub_key, driver.priv_key),
            }

    @property
    def _slots(self):
        return self._driver.slots

    @property
    def driver(self):
        return None

    def _build_certificate(self, pub_key, priv_key):
        name = x509.Name(
            [x509.NameAttribute(x509.NameOID.COMMON_NAME, self.__class__.__name__)]
        )
        now = datetime.datetime.utcnow()
        return (
            x509.CertificateBuilder()
            .subject_name(name)
            .issuer_name(name)
            .public_key(pub_key)
            .serial_number(self._driver.serial)
            .not_valid_before(now)
            .not_valid_after(now + datetime.timedelta(days=365))
            .sign(priv_key, hashes.SHA256(), default_backend())
        )

    def authenticate(self, key_type, management_key):
        if management_key != self._driver.management_key:
            raise ApduError(b"", SW.SECURITY_CONDITION_NOT_SATISFIED)

    def set_management_key(self, key_type, management_key, touch=False):
        self._driver.management_key = management_key

    def change_pin(self, old_pin, new_pin):
        if old_pin != self._driver.pin:
            raise InvalidPinError(0)
        self._driver.pin = new_pin

    def change_puk(self, *args, **kwargs):
        pass

    def generate_self_signed_certificate(self, *args, **kwargs):
        pass

    def get_pin_tries(self):
        return 1

    def put_key(self, slot, private_key, pin_policy=None, touch_policy=None):
        self._slots[slot] = {
            "priv_key": private_key,
            "pub_key": private_key.public_key(),
            "cert": None,
        }

    def put_certificate(self, slot, cert):
        self._slots.setdefault(slot, {})["cert"] = cert

    def get_certificate(self, slot):
        slot_data = self._slots.get(slot)
        if not slot_data or slot_data.get("cert") is None:
            raise ApduError(b"", SW.FILE_NOT_FOUND)
        return slot_data["cert"]

    def get_slot_metadata(self, slot):
        slot_data = self._slots.get(slot)
        if not slot_data or slot_data.get("priv_key") is None:
            raise ApduError(b"", SW.FILE_NOT_FOUND)
        # the actual metadata fields aren't modeled - callers only care
        # whether this raises or not
        return object()

    def reset(self):
        self._driver.slots.clear()
        self._driver.data_objects.clear()
        self._driver.pin_verified = False
        self._driver.management_key = DEFAULT_MANAGEMENT_KEY
        self._driver.pin = VALID_PIN

    def get_object(self, object_id):
        if (
            object_id == OBJECT_ID_PIVMAN_PROTECTED_DATA
            and not self._driver.pin_verified
        ):
            raise ApduError(b"", SW.SECURITY_CONDITION_NOT_SATISFIED)
        data = self._driver.data_objects.get(object_id)
        if data is None:
            raise ApduError(b"", SW.FILE_NOT_FOUND)
        return data

    def put_object(self, object_id, data):
        if (
            object_id == OBJECT_ID_PIVMAN_PROTECTED_DATA
            and not self._driver.pin_verified
        ):
            raise ApduError(b"", SW.SECURITY_CONDITION_NOT_SATISFIED)
        self._driver.data_objects[object_id] = data

    def set_pin_retries(self, *args, **kwargs):
        pass

    def set_pin_attempts(self, *args, **kwargs):
        pass

    def sign(self, slot, key_type, data, hash, padding):
        """Sign data using the same function as TUF"""
        if isinstance(data, str):
            data = data.encode("utf-8")

        slot_data = self._slots.get(slot)
        priv_key = slot_data["priv_key"] if slot_data else self._driver.priv_key
        return priv_key.sign(data, padding, hash)

    def verify_pin(self, pin):
        if self._driver.pin != pin:
            raise InvalidPinError(0)
        self._driver.pin_verified = True


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
def _yk_piv_ctrl_mock(serial=None):
    global INSERTED_YUBIKEY

    if INSERTED_YUBIKEY is None:
        raise ValueError("No YubiKey found with the given interface(s)")

    yield [(FakePivController(INSERTED_YUBIKEY), INSERTED_YUBIKEY.serial)]
