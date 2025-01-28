import datetime
from contextlib import contextmanager
from functools import wraps
from getpass import getpass
from pathlib import Path
from typing import Callable, Optional

import click
from cryptography import x509
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.serialization import load_pem_private_key
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import rsa, padding

from taf.tuf.keys import get_sslib_key_from_value
from taf.yubikey.yubikey_manager import PinManager
from ykman.device import list_all_devices
from yubikit.core.smartcard import SmartCardConnection
from ykman.piv import (
    KEY_TYPE,
    MANAGEMENT_KEY_TYPE,
    SLOT,
    PivSession,
    generate_random_management_key,
)
from yubikit.piv import (
    DEFAULT_MANAGEMENT_KEY,
    PIN_POLICY,
    InvalidPinError,
)

from taf.constants import DEFAULT_RSA_SIGNATURE_SCHEME
from taf.exceptions import InvalidPINError, YubikeyError
from taf.utils import get_pin_for
from taf.log import taf_logger

from securesystemslib.signer._key import SSlibKey

DEFAULT_PIN = "123456"
DEFAULT_PUK = "12345678"
EXPIRATION_INTERVAL = 36500


def raise_yubikey_err(msg: Optional[str] = None) -> Callable:
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
def _yk_piv_ctrl(serial=None):
    """Context manager to open connection and instantiate Piv Session.

    Args:
        - serial (str): Match Yubikey's serial multiple keys are inserted

    Returns:
        - ykman.piv.PivSession

    Raises:
        - YubikeyError
    """
    sessions = []
    devices_info = []
    try:
        for dev, info in list_all_devices():
            if serial is None or info.serial == serial:
                connection = dev.open_connection(SmartCardConnection)
                try:
                    session = PivSession(connection)
                    sessions.append((session, info.serial))
                    devices_info.append(
                        (connection, session)
                    )  # Store to manage cleanup
                    if serial is not None:
                        break
                except Exception as e:
                    connection.close()  # Ensure we close connection on error
                    raise e
        if serial is not None:
            session, serial = sessions[0]
            yield session, serial
        else:
            yield sessions
    finally:
        # Cleanup: ensure all connections are closed properly
        for connection, _ in devices_info:
            connection.close()


def is_inserted():
    """Checks if YubiKey is inserted.

    Args:
        None

    Returns:
        True if at least one Yubikey is inserted (bool)

    Raises:
        - YubikeyError
    """
    return len(list(list_all_devices())) > 0


@raise_yubikey_err()
def is_valid_pin(pin, serial):
    """Checks if given pin is valid.

    Args:
        pin(str): Yubikey piv PIN

    Returns:
        tuple: True if PIN is valid, otherwise False, number of PIN retries

    Raises:
        - YubikeyError
    """
    if serial is None:
        serials = get_serial_num()
        if len(serials) != 1:
            raise YubikeyError(
                "Please insert exactly one YubiKey or specify a serial number of the YubiKey whose pin is to be checked"
            )
        serial = serials[0]
    with _yk_piv_ctrl(serial=serial) as (ctrl, _):
        try:
            ctrl.verify_pin(pin)
            return True, None  # ctrl.get_pin_tries() fails if PIN is valid
        except InvalidPinError:
            return False, ctrl.get_pin_attempts()


@raise_yubikey_err("Cannot get serial number.")
def get_serial_num():
    """Get serial numbers of all isnerted YubiKeys

    Args:
        - pub_key_pem(str): Match Yubikey's public key (PEM) if multiple keys
                            are inserted

    Returns:
        Yubikey serial number

    Raises:
        - YubikeyError
    """
    serials = []
    with _yk_piv_ctrl() as sessions:
        for _, serial in sessions:
            # Process each session
            serials.append(serial)
    return serials


@raise_yubikey_err("Cannot export x509 certificate.")
def export_piv_x509(cert_format=serialization.Encoding.PEM, serial=None):
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
    with _yk_piv_ctrl(serial=serial) as (ctrl, _):
        x509 = ctrl.get_certificate(SLOT.SIGNATURE)
        return x509.public_bytes(encoding=cert_format)


@raise_yubikey_err("Cannot export public key.")
def export_piv_pub_key(pub_key_format=serialization.Encoding.PEM, serial=None):
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
    with _yk_piv_ctrl(serial=serial) as (ctrl, _):
        try:
            x509_cert = ctrl.get_certificate(SLOT.SIGNATURE)
            public_key = x509_cert.public_key()
            return public_key.public_bytes(
                encoding=pub_key_format,
                format=serialization.PublicFormat.SubjectPublicKeyInfo,
            )
        except Exception as e:
            raise YubikeyError(f"Failed to export public key: {str(e)}") from e


@raise_yubikey_err("Cannot export yk certificate.")
def export_yk_certificate(certs_dir, key: SSlibKey, serial: str):
    if certs_dir is None:
        certs_dir = Path.home()
    else:
        certs_dir = Path(certs_dir)
    certs_dir.mkdir(parents=True, exist_ok=True)
    cert_path = certs_dir / f"{key.keyid}.cert"
    print(f"Exporting certificate to {cert_path}")
    with open(cert_path, "wb") as f:
        f.write(export_piv_x509(serial=serial))


def get_and_validate_pin(key_name, pin_confirm=True, pin_repeat=True, serial=None):
    valid_pin = False
    while not valid_pin:
        pin = get_pin_for(key_name, pin_confirm, pin_repeat)
        valid_pin, retries = is_valid_pin(pin, serial)
        if not valid_pin and not retries:
            raise InvalidPINError("No retries left. YubiKey locked.")
        if not valid_pin:
            if not click.confirm(
                f"Incorrect PIN. Do you want to try again? {retries} retires left."
            ):
                raise InvalidPINError("PIN input cancelled")
    return pin


@raise_yubikey_err("Cannot get public key in TUF format.")
def get_piv_public_key_tuf(
    scheme=DEFAULT_RSA_SIGNATURE_SCHEME, serial=None
) -> SSlibKey:
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
    pub_key_pem = export_piv_pub_key(serial=serial).decode("utf-8")
    return get_sslib_key_from_value(pub_key_pem, scheme)


def list_connected_yubikeys():
    """Lists all connected YubiKeys with their serial numbers and details."""
    yubikeys = list_all_devices()
    if not yubikeys:
        print("No YubiKeys connected.")
    else:
        for index, (_, info) in enumerate(yubikeys, start=1):
            print(f"YubiKey {index}:")
            print(f"  Serial Number: {info.serial}")
            print(f"  Version: {info.version}")
            print(f"  Form Factor: {info.form_factor}")


def _read_and_check_single_yubikey(
    role,
    key_name,
    taf_repo,
    pin_manager,
    registering_new_key,
    creating_new_key,
    pin_confirm,
    pin_repeat,
    prompt_message,
    retrying,
    yubikeys_to_skip,
):

    if retrying:
        if prompt_message is None:
            prompt_message = f"Please insert {key_name} YubiKey and press ENTER"
        getpass(prompt_message)

    if not yubikeys_to_skip:
        yubikeys_to_skip = []

    # make sure that YubiKey is inserted
    try:
        serials = get_serial_num()

        if taf_repo is None:
            # if setting up a YubiKey outside of the creation of a new repository or addition of new roles
            if len(serials) > 1:
                print("\nPlease insert only one YubiKey\n")
                return
        else:
            not_loaded = [
                serial
                for serial in serials
                if not taf_repo.yubikey_store.is_loaded_for_role(serial, role) and serial not in yubikeys_to_skip
            ]

            if len(not_loaded) != 1:
                print("\nPlease insert only one not previously inserted YubiKey\n")
                return None

            if not len(not_loaded):
                return None

            # no need to try loading keys that we know were previously loaded
            serials = not_loaded

    except Exception:
        taf_logger.log("NOTICE", "No YubiKeys inserted")
        return None

    serial_num = serials[0]
    # check if this key is already loaded as the provided role's key (we can use the same key
    # to sign different metadata)
    # read the public key, unless a new key needs to be generated on the yubikey
    public_key = (
        get_piv_public_key_tuf(serial=serial_num) if not creating_new_key else None
    )
    # check if this yubikey is can be used for signing the provided role's metadata
    # if the key was already registered as that role's key
    if not registering_new_key and role is not None and taf_repo is not None:
        if not taf_repo.is_valid_metadata_yubikey(role, public_key):
            return None

    if pin_manager.get_pin(serial_num) is None:
        if creating_new_key:
            pin = get_pin_for(key_name, pin_confirm, pin_repeat)
        else:
            pin = get_and_validate_pin(key_name, pin_confirm, pin_repeat, serial_num)

        pin_manager.add_pin(serial_num, pin)

    if taf_repo is not None:
        # when reusing the same yubikey, public key will already be in the public keys dictionary
        # but the key name still needs to be added to the key id mapping dictionary
        taf_repo.yubikey_store.add_key_data(key_name, serial_num, public_key, role)

    return public_key, serial_num, key_name


def _read_and_check_yubikeys(
    role,
    taf_repo,
    pin_manager,
    pin_confirm,
    pin_repeat,
    prompt_message,
    key_names,
    retrying,
    hide_already_loaded_message,
    hide_threshold_message,
):
    if retrying:
        if prompt_message is None:
            if not hide_threshold_message:
                threshold = taf_repo.get_role_threshold(role)
                prompt_message = f"Please insert {role} ({', '.join(key_names)}) YubiKey(s) (threshold {threshold}) and press ENTER"
            else:
                prompt_message = f"Please insert {role} ({', '.join(key_names)}) YubiKey(s) and press ENTER"
        getpass(prompt_message)

    # make sure that YubiKey is inserted
    try:
        serials = get_serial_num()
    except Exception:
        taf_logger.log("NOTICE", "No YubiKeys inserted")
        return None

    if not len(serials):
        return None

    # check if this key is already loaded as the provided role's key (we can use the same key
    # to sign different metadata)
    yubikeys = []
    invalid_keys = []
    all_loaded = True
    for index, serial_num in enumerate(serials):
        if not taf_repo.yubikey_store.is_loaded(serial_num):
            all_loaded = False
            # read the public key, unless a new key needs to be generated on the yubikey
            public_key = get_piv_public_key_tuf(serial=serial_num)
            # check if this yubikey is can be used for signing the provided role's metadata
            # if the key was already registered as that role's key
            if role is not None and taf_repo is not None:
                if not taf_repo.is_valid_metadata_yubikey(role, public_key):
                    invalid_keys.append(serial_num)
                    # print(f"The inserted YubiKey is not a valid {role} key")
                    continue

            if taf_repo.keys_name_mappings:
                key_name = taf_repo.keys_name_mappings.get(public_key.keyid)
            else:
                key_name = key_names[index]

            if pin_manager.get_pin(serial_num) is None:
                pin = get_and_validate_pin(
                    key_name, pin_confirm, pin_repeat, serial_num
                )
                pin_manager.add_pin(serial_num, pin)

            # when reusing the same yubikey, public key will already be in the public keys dictionary
            # but the key name still needs to be added to the key id mapping dictionary
            taf_repo.yubikey_store.add_key_data(key_name, serial_num, public_key, role)
            yubikeys.append((public_key, serial_num, key_name))

    if not hide_already_loaded_message and all_loaded:
        print("All inserted YubiKeys already loaded")

    return yubikeys


@raise_yubikey_err("Cannot sign data.")
def sign_piv_rsa_pkcs1v15(data, pin, serial=None):
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
    with _yk_piv_ctrl(serial=serial) as (ctrl, _):
        ctrl.verify_pin(pin)
        return ctrl.sign(
            SLOT.SIGNATURE, KEY_TYPE.RSA2048, data, hashes.SHA256(), padding.PKCS1v15()
        )


@raise_yubikey_err("Cannot setup Yubikey.")
def setup(
    pin,
    serial,
    cert_cn,
    cert_exp_days=365,
    pin_retries=10,
    private_key_pem=None,
    mgm_key=generate_random_management_key(MANAGEMENT_KEY_TYPE.TDES),
    key_size=2048,
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

    with _yk_piv_ctrl(serial=serial) as (ctrl, _):
        # Factory reset and set PINs
        ctrl.reset()

        ctrl.authenticate(MANAGEMENT_KEY_TYPE.TDES, DEFAULT_MANAGEMENT_KEY)
        ctrl.set_management_key(MANAGEMENT_KEY_TYPE.TDES, mgm_key)

        # Generate RSA2048
        if private_key_pem is None:
            private_key = rsa.generate_private_key(65537, key_size, default_backend())
            pub_key = private_key.public_key()
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

        ctrl.put_key(SLOT.SIGNATURE, private_key, PIN_POLICY.ALWAYS)
        pub_key = private_key.public_key()
        ctrl.authenticate(MANAGEMENT_KEY_TYPE.TDES, mgm_key)
        ctrl.verify_pin(DEFAULT_PIN)

        now = datetime.datetime.now()
        valid_to = now + datetime.timedelta(days=cert_exp_days)

        name = x509.Name([x509.NameAttribute(x509.NameOID.COMMON_NAME, cert_cn)])
        # Generate and import certificate
        cert = (
            x509.CertificateBuilder()
            .subject_name(name)
            .issuer_name(name)
            .public_key(pub_key)
            .serial_number(x509.random_serial_number())
            .not_valid_before(now)
            .not_valid_after(valid_to)
            .sign(private_key, hashes.SHA256(), default_backend())
        )

        ctrl.put_certificate(SLOT.SIGNATURE, cert)

        ctrl.set_pin_attempts(pin_attempts=pin_retries, puk_attempts=pin_retries)
        ctrl.change_pin(DEFAULT_PIN, pin)
        ctrl.change_puk(DEFAULT_PUK, pin)

    return pub_key.public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
    )


def setup_new_yubikey(
    pin_manager: PinManager,
    serial: str,
    scheme: Optional[str] = DEFAULT_RSA_SIGNATURE_SCHEME,
    key_size: Optional[int] = 2048,
) -> SSlibKey:
    pin = pin_manager.get_pin(serial)
    cert_cn = input("Enter key holder's name: ")
    print("Generating key, please wait...")
    pub_key_pem = setup(
        pin, serial, cert_cn, cert_exp_days=EXPIRATION_INTERVAL, key_size=key_size
    ).decode("utf-8")
    scheme = DEFAULT_RSA_SIGNATURE_SCHEME
    key = get_sslib_key_from_value(pub_key_pem, scheme)
    return key


def verify_yk_inserted(serial_num, key_name):
    def _check_if_yk_inserted():
        try:
            serials = get_serial_num()
        except Exception:
            return False

        return serial_num in serials

    while not _check_if_yk_inserted():
        prompt_message = f"Please insert {key_name} YubiKey and press ENTER"
        getpass(prompt_message)


def yubikey_prompt(
    key_names,
    pin_manager,
    role=None,
    taf_repo=None,
    registering_new_key=False,
    creating_new_key=False,
    pin_confirm=True,
    pin_repeat=True,
    prompt_message=None,
    retry_on_failure=True,
    hide_already_loaded_message=False,
    hide_threshold_message=False,
    yubikeys_to_skip=None,
):

    retry_counter = 0
    yubikeys = None
    while True:
        retrying = retry_counter > 0
        if registering_new_key or creating_new_key:
            yubikey = _read_and_check_single_yubikey(
                role,
                key_names[0],
                taf_repo,
                pin_manager,
                registering_new_key,
                creating_new_key,
                pin_confirm,
                pin_repeat,
                prompt_message,
                retrying,
                yubikeys_to_skip,
            )
            if yubikey:
                yubikeys = [yubikey]
        else:
            yubikeys = _read_and_check_yubikeys(
                role,
                taf_repo,
                pin_manager,
                pin_confirm,
                pin_repeat,
                prompt_message,
                key_names,
                retrying,
                hide_already_loaded_message,
                hide_threshold_message,
            )

        if not yubikeys and not retry_on_failure:
            return [(None, None, None)]
        if yubikeys:
            return yubikeys
        retry_counter += 1


def yk_secrets_handler(prompt, pin_manager, serial_num):
    if prompt == "pin":
        return pin_manager.get_pin(serial_num)
    raise YubikeyError(f"Invalid prompt {prompt}")
