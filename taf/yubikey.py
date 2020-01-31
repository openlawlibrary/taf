import datetime
from contextlib import contextmanager
from functools import wraps
from collections import defaultdict
from getpass import getpass

import click
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.serialization import load_pem_private_key
from tuf.repository_tool import import_rsakey_from_pem
from ykman.descriptor import list_devices, open_device
from ykman.piv import (
    ALGO,
    DEFAULT_MANAGEMENT_KEY,
    PIN_POLICY,
    SLOT,
    PivController,
    WrongPin,
    generate_random_management_key,
)
from ykman.util import TRANSPORT

from taf.constants import DEFAULT_RSA_SIGNATURE_SCHEME
from taf.exceptions import InvalidPINError, YubikeyError
from taf.utils import get_pin_for

DEFAULT_PIN = "123456"
DEFAULT_PUK = "12345678"
EXPIRATION_INTERVAL = 36500

_yks_data_dict = defaultdict(dict)


def add_key_pin(serial_num, pin):
    _yks_data_dict[serial_num]["pin"] = pin


def add_key_public_key(serial_num, public_key):
    _yks_data_dict[serial_num]["public_key"] = public_key


def get_key_pin(serial_num):
    if serial_num in _yks_data_dict:
        return _yks_data_dict.get(serial_num).get("pin")
    return None


def get_key_public_key(serial_num):
    if serial_num in _yks_data_dict:
        return _yks_data_dict.get(serial_num).get("public_key")
    return None


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
                err_msg = (
                    f"{msg} Reason: ({type(e).__name__}) {str(e)}" if msg else str(e)
                )
                raise YubikeyError(err_msg) from e

        return decorator

    return wrapper


@contextmanager
def _yk_piv_ctrl(serial=None, pub_key_pem=None):
    """Context manager to open connection and instantiate piv controller.

    Args:
        - pub_key_pem(str): Match Yubikey's public key (PEM) if multiple keys
                            are inserted

    Returns:
        - ykman.piv.PivController

    Raises:
        - YubikeyError
    """
    # If pub_key_pem is given, iterate all devices, read x509 certs and try to match
    # public keys.
    if pub_key_pem is not None:
        for yk in list_devices(transports=TRANSPORT.CCID):
            yk_ctrl = PivController(yk.driver)
            device_pub_key_pem = (
                yk_ctrl.read_certificate(SLOT.SIGNATURE)
                .public_key()
                .public_bytes(
                    encoding=serialization.Encoding.PEM,
                    format=serialization.PublicFormat.SubjectPublicKeyInfo,
                )
                .decode("utf-8")
            )
            # Tries to match without last newline char
            if (
                device_pub_key_pem == pub_key_pem
                or device_pub_key_pem[:-1] == pub_key_pem
            ):
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
def get_serial_num(pub_key_pem=None):
    """Get Yubikey serial number.

    Args:
        - pub_key_pem(str): Match Yubikey's public key (PEM) if multiple keys
                            are inserted

    Returns:
        Yubikey serial number

    Raises:
        - YubikeyError
    """
    with _yk_piv_ctrl(pub_key_pem=pub_key_pem) as (_, serial):
        return serial


@raise_yubikey_err("Cannot export x509 certificate.")
def export_piv_x509(cert_format=serialization.Encoding.PEM, pub_key_pem=None):
    """Exports YubiKey's piv slot x509.

    Args:
        - cert_format(str): One of 'serialization.Encoding' formats.
        - pub_key_pem(str): Match Yubikey's public key (PEM) if multiple keys
                            are inserted

    Returns:
        PIV x509 certificate in a given format (bytes)

    Raises:
        - YubikeyError
    """
    with _yk_piv_ctrl(pub_key_pem=pub_key_pem) as (ctrl, _):
        x509 = ctrl.read_certificate(SLOT.SIGNATURE)
        return x509.public_bytes(encoding=cert_format)


@raise_yubikey_err("Cannot export public key.")
def export_piv_pub_key(pub_key_format=serialization.Encoding.PEM, pub_key_pem=None):
    """Exports YubiKey's piv slot public key.

    Args:
        - pub_key_format(str): One of 'serialization.Encoding' formats.
        - pub_key_pem(str): Match Yubikey's public key (PEM) if multiple keys
                            are inserted

    Returns:
        PIV public key in a given format (bytes)

    Raises:
        - YubikeyError
    """
    with _yk_piv_ctrl(pub_key_pem=pub_key_pem) as (ctrl, _):
        x509 = ctrl.read_certificate(SLOT.SIGNATURE)
        return x509.public_key().public_bytes(
            encoding=pub_key_format,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )


@raise_yubikey_err("Cannot get public key in TUF format.")
def get_piv_public_key_tuf(scheme=DEFAULT_RSA_SIGNATURE_SCHEME, pub_key_pem=None):
    """Return public key from a Yubikey in TUF's RSAKEY_SCHEMA format.

    Args:
        - scheme(str): Rsa signature scheme (default is rsa-pkcs1v15-sha256)
        - pub_key_pem(str): Match Yubikey's public key (PEM) if multiple keys
                            are inserted

    Returns:
        A dictionary containing the RSA keys and other identifying information
        from inserted smart card.
        Conforms to 'securesystemslib.formats.RSAKEY_SCHEMA'.

    Raises:
        - YubikeyError
    """
    pub_key_pem = export_piv_pub_key(pub_key_pem=pub_key_pem).decode("utf-8")
    return import_rsakey_from_pem(pub_key_pem, scheme)


@raise_yubikey_err("Cannot sign data.")
def sign_piv_rsa_pkcs1v15(data, pin, pub_key_pem=None):
    """Sign data with key from YubiKey's piv slot.

    Args:
        - data(bytes): Data to be signed
        - pin(str): Pin for piv slot login.
        - pub_key_pem(str): Match Yubikey's public key (PEM) if multiple keys
                            are inserted

    Returns:
        Signature (bytes)

    Raises:
        - YubikeyError
    """
    with _yk_piv_ctrl(pub_key_pem=pub_key_pem) as (ctrl, _):
        ctrl.verify(pin)
        return ctrl.sign(SLOT.SIGNATURE, ALGO.RSA2048, data)


@raise_yubikey_err("Cannot setup Yubikey.")
def setup(
    pin,
    cert_cn,
    cert_exp_days=365,
    pin_retries=10,
    private_key_pem=None,
    mgm_key=generate_random_management_key(),
):
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
            try:
                private_key = load_pem_private_key(
                    private_key_pem, None, default_backend()
                )
            except TypeError:
                pem_pwd = getpass("Enter pem file password:\n")
                if pem_pwd:
                    pem_pwd = pem_pwd.encode()
                private_key = load_pem_private_key(
                    private_key_pem, pem_pwd, default_backend()
                )

            ctrl.import_key(SLOT.SIGNATURE, private_key, PIN_POLICY.ALWAYS)
            pub_key = private_key.public_key()

        ctrl.authenticate(mgm_key)
        ctrl.verify(DEFAULT_PIN)

        # Generate and import certificate
        now = datetime.datetime.now()
        valid_to = now + datetime.timedelta(days=cert_exp_days)
        ctrl.generate_self_signed_certificate(
            SLOT.SIGNATURE, pub_key, cert_cn, now, valid_to
        )

        ctrl.set_pin_retries(pin_retries=pin_retries, puk_retries=pin_retries)
        ctrl.change_pin(DEFAULT_PIN, pin)
        ctrl.change_puk(DEFAULT_PUK, pin)

    return pub_key.public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
    )


def setup_new_yubikey(serial_num, scheme=DEFAULT_RSA_SIGNATURE_SCHEME):
    pin = get_key_pin(serial_num)
    cert_cn = input("Enter key holder's name: ")
    print("Generating key, please wait...")
    pub_key_pem = setup(pin, cert_cn, cert_exp_days=EXPIRATION_INTERVAL).decode("utf-8")
    scheme = DEFAULT_RSA_SIGNATURE_SCHEME
    key = import_rsakey_from_pem(pub_key_pem, scheme)
    return key


def get_and_validate_pin(key_name, pin_confirm=True, pin_repeat=True):
    valid_pin = False
    while not valid_pin:
        pin = get_pin_for(key_name, pin_confirm, pin_repeat)
        valid_pin, retries = is_valid_pin(pin)
        if not valid_pin and not retries:
            raise InvalidPINError("No retries left. YubiKey locked.")
        if not valid_pin:
            if not click.confirm(
                f"Incorrect PIN. Do you want to try again? {retries} retires left."
            ):
                raise InvalidPINError("PIN input cancelled")
    return pin


def yubikey_prompt(
    key_name,
    role=None,
    taf_repo=None,
    registering_new_key=False,
    creating_new_key=False,
    loaded_yubikeys=None,
    pin_confirm=True,
    pin_repeat=True,
    prompt_message=None,
):
    def _read_and_check_yubikey(
        key_name,
        role,
        taf_repo,
        registering_new_key,
        creating_new_key,
        loaded_yubikeys,
        pin_confirm,
        pin_repeat,
        prompt_message,
    ):

        if prompt_message is None:
            prompt_message = f"Please insert {key_name} YubiKey and press ENTER"
        input(prompt_message)
        # make sure that YubiKey is inserted
        try:
            serial_num = get_serial_num()
        except Exception:
            print("YubiKey not inserted")
            return False, None, None

        # check if this key is already loaded as the provided role's key (we can use the same key
        # to sign different metadata)
        if (
            loaded_yubikeys is not None
            and serial_num in loaded_yubikeys
            and role in loaded_yubikeys[serial_num]
        ):
            print("Key already loaded")
            return False, None, None

        # read the public key, unless a new key needs to be generated on the yubikey
        public_key = get_piv_public_key_tuf() if not creating_new_key else None
        # check if this yubikey is can be used for signing the provided role's metadata
        # if the key was already registered as that role's key
        if not registering_new_key and role is not None and taf_repo is not None:
            if not taf_repo.is_valid_metadata_yubikey(role, public_key):
                print(f"The inserted YubiKey is not a valid {role} key")
                return False, None, None

        if get_key_pin(serial_num) is None:
            if creating_new_key:
                pin = get_pin_for(key_name, pin_confirm, pin_repeat)
            else:
                pin = get_and_validate_pin(key_name, pin_confirm, pin_repeat)
            add_key_pin(serial_num, pin)

        if get_key_public_key(serial_num) is None and public_key is not None:
            add_key_public_key(serial_num, public_key)

        if role is not None:
            if loaded_yubikeys is None:
                loaded_yubikeys = {serial_num: [role]}
            else:
                loaded_yubikeys.setdefault(serial_num, []).append(role)

        return True, public_key, serial_num

    while True:
        success, key, serial_num = _read_and_check_yubikey(
            key_name,
            role,
            taf_repo,
            registering_new_key,
            creating_new_key,
            loaded_yubikeys,
            pin_confirm,
            pin_repeat,
            prompt_message,
        )
        if success:
            return key, serial_num
