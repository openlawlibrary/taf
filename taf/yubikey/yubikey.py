import click
import datetime
import os
from contextlib import contextmanager
from functools import wraps
from getpass import getpass
from pathlib import Path
from typing import Callable, Optional, Tuple

from cryptography import x509
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.serialization import load_pem_private_key
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from taf.api.utils._conf import find_taf_directory
from taf.tuf.keys import (
    _get_legacy_keyid,
    generate_keypair,
    get_public_key_pem,
    get_sslib_key_from_value,
    is_rsa_scheme,
    is_same_public_key,
)
from taf.yubikey.yubikey_manager import PinManager
from taf.models.types import KeysMapping
from ykman.device import list_all_devices
from yubikit.core import NotSupportedError
from yubikit.core.smartcard import ApduError, SW, SmartCardConnection
from ykman.piv import (
    KEY_TYPE,
    MANAGEMENT_KEY_TYPE,
    SLOT,
    PivSession,
    get_pivman_protected_data,
)
from yubikit.piv import (
    DEFAULT_MANAGEMENT_KEY,
    PIN_POLICY,
    TOUCH_POLICY,
    InvalidPinError,
)

from taf.config import load_config
from taf.exceptions import (
    InvalidConfigError,
    InvalidPINError,
    SchemeNotSpecifiedError,
    YubikeyError,
)
from taf.utils import get_pin_for
from taf.log import taf_logger

from securesystemslib.signer._key import SSlibKey

EXPIRATION_INTERVAL = 36500

# Retired slots (RETIRED1-RETIRED20) are reserved for key history/decryption, not signing.
SETUP_SLOTS = {SLOT.SIGNATURE, SLOT.AUTHENTICATION, SLOT.KEY_MANAGEMENT, SLOT.CARD_AUTH}


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
    taf_logger.debug(f"Entering _yk_piv_ctrl context manager with serial={serial}")
    sessions = []
    devices_info = []
    found_serials = []
    try:
        for dev, info in list_all_devices():
            taf_logger.debug(f"Found device with info serial={info.serial}")
            found_serials.append(info.serial)
            if serial is None or info.serial == serial:
                connection = dev.open_connection(SmartCardConnection)
                try:
                    session = PivSession(connection)
                    sessions.append((session, info.serial))
                    devices_info.append((connection, session))
                    if serial is not None:
                        break
                except Exception as e:
                    connection.close()  # Ensure we close connection on error
                    raise e
        if serial is not None:
            if not sessions:
                if not found_serials:
                    raise YubikeyError("No YubiKeys were detected.")
                raise YubikeyError(
                    f"YubiKey with serial number {serial} was not detected. "
                    f"Detected serial numbers: {', '.join(str(s) for s in found_serials)}"
                )
            session, serial = sessions[0]
            taf_logger.debug(f"Yielding single session for serial={serial}")
            yield [(session, serial)]
        else:
            taf_logger.debug(f"Yielding all sessions: {[s[1] for s in sessions]}")
            yield sessions
    finally:
        # Cleanup: ensure all connections are closed properly
        for connection, _ in devices_info:
            taf_logger.debug("Closing SmartCardConnection.")
            connection.close()


@raise_yubikey_err()
def is_valid_pin(pin: str, serial: Optional[str] = None):
    """Checks if given pin is valid.

    Args:
        pin(str): Yubikey piv PIN

    Returns:
        tuple: True if PIN is valid, otherwise False, number of PIN retries

    Raises:
        - YubikeyError
    """
    taf_logger.debug(f"Validating PIN for serial={serial}")
    if serial is None:
        serials = get_serial_nums()
        if len(serials) != 1:
            raise YubikeyError(
                "Please insert exactly one YubiKey or specify a serial number of the YubiKey whose pin is to be checked"
            )
        serial = serials[0]
    with _yk_piv_ctrl(serial=serial) as [(ctrl, _)]:
        try:
            ctrl.verify_pin(pin)
            taf_logger.debug(f"PIN is valid for serial={serial}")
            return True, None  # ctrl.get_pin_tries() fails if PIN is valid
        except InvalidPinError:
            tries_left = ctrl.get_pin_attempts()
            taf_logger.debug(
                f"Invalid PIN for serial={serial}, tries left = {tries_left}"
            )
            return False, tries_left


@raise_yubikey_err("Cannot get serial number.")
def get_serial_nums():
    """Get serial numbers of all inserted  YubiKeys

    Args:
        - pub_key_pem(str): Match Yubikey's public key (PEM) if multiple keys
                            are inserted

    Returns:
        Yubikey serial numbers

    Raises:
        - YubikeyError
    """
    serials = []
    with _yk_piv_ctrl() as sessions:
        for _, serial in sessions:
            taf_logger.debug(f"Discovered YubiKey with serial={serial}")
            serials.append(serial)
    return serials


@raise_yubikey_err("Cannot export x509 certificate.")
def export_piv_x509(
    cert_format=serialization.Encoding.PEM, serial=None, slot=SLOT.SIGNATURE
):
    """Exports YubiKey's piv slot x509.

    Args:
        - cert_format(str): One of 'serialization.Encoding' formats.
        - pub_key_pem(str): Match Yubikey's public key (PEM) if multiple keys
                            are inserted
        - slot(SLOT): The PIV slot to read the certificate from. Defaults to
                      SLOT.SIGNATURE.

    Returns:
        PIV x509 certificate in a given format (bytes)

    Raises:
        - YubikeyError
    """
    taf_logger.debug(f"Exporting X509 certificate for serial={serial}, slot={slot}")
    with _yk_piv_ctrl(serial=serial) as [(ctrl, _)]:
        x509_cert = ctrl.get_certificate(slot)
        return x509_cert.public_bytes(encoding=cert_format)


def _public_key_pem(cert) -> str:
    """Return the public key of a PIV slot's certificate in PEM format"""
    return (
        cert.public_key()
        .public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        .decode("utf-8")
    )


@raise_yubikey_err("Cannot export public key.")
def export_piv_pub_key(serial=None, slot=SLOT.SIGNATURE) -> str:
    """Exports YubiKey's piv slot public key.

    Args:
        - pub_key_pem(str): Match Yubikey's public key (PEM) if multiple keys
                            are inserted
        - slot(SLOT): The PIV slot holding the key. Defaults to SLOT.SIGNATURE.

    Returns:
        PIV public key in PEM format

    Raises:
        - YubikeyError
    """
    taf_logger.debug(f"Exporting public key for serial={serial}")
    with _yk_piv_ctrl(serial=serial) as [(ctrl, _)]:
        try:
            return _public_key_pem(ctrl.get_certificate(slot))
        except Exception as e:
            raise YubikeyError(f"Failed to export public key: {str(e)}") from e


@raise_yubikey_err("Cannot export yk certificate.")
def export_yk_certificate(certs_dir, key: SSlibKey, serial: str, slot=SLOT.SIGNATURE):
    if certs_dir is None:
        certs_dir = Path.home()
    else:
        certs_dir = Path(certs_dir)
    certs_dir.mkdir(parents=True, exist_ok=True)
    cert_path = certs_dir / f"{key.keyid}.cert"
    print(f"Exporting certificate to {cert_path}")
    taf_logger.debug(f"Writing certificate file for keyid={key.keyid}, serial={serial}")
    with open(cert_path, "wb") as f:
        f.write(export_piv_x509(serial=serial, slot=slot))


def get_and_validate_pin(
    key_name,
    pin_confirm=True,
    pin_repeat=True,
    serial=None,
    key_id_pins=None,
    public_key=None,
):
    valid_pin = False

    if key_id_pins and public_key:
        key_id = _get_legacy_keyid(public_key)
        pin = key_id_pins.get(key_id)
    else:
        pin = None

    while not valid_pin:
        if not pin:
            pin = get_pin_for(key_name, pin_confirm, pin_repeat)

        valid_pin, retries = is_valid_pin(pin, serial)
        if not valid_pin and not retries:
            taf_logger.debug(f"PIN invalid and no retries left for serial={serial}")
            raise InvalidPINError("No retries left. YubiKey locked.")
        if not valid_pin:
            if not click.confirm(
                f"Incorrect PIN. Do you want to try again? {retries} retires left."
            ):
                taf_logger.debug("User cancelled PIN input.")
                raise InvalidPINError("PIN input cancelled")
            pin = None
    return pin


def get_pin_from_env(
    public_key: Optional[SSlibKey], serial_num: int, taf_dir: Optional[Path]
) -> Optional[str]:
    """Get PIN from environment variables.
    The PIN is stored in an environment variable named after either:

    i) the serial number of the YubiKey, or
    ii) the key name in uppercase, with hyphens replaced by underscores.

    For example, If the serial number is "123456", the environment variable would be "PIN_123456".
    Moreover, if the key name is "my-key", the environment variable
    would be "PIN_MY_KEY".
    If the key name is not found in the environment variables, the function
    returns None.
    """
    from taf.auth_repo import AuthenticationRepository

    pin = os.environ.get(f"PIN_{serial_num}")
    if pin is not None:
        return pin

    try:
        if taf_dir is None:
            raise FileNotFoundError(
                "No .taf directory found in the current working directory."
            )
        cfg = load_config(taf_dir / "config.toml")
        if cfg.root is None:
            raise FileNotFoundError("No root authentication repository found.")
        taf_logger.debug(f"Config loaded: {cfg}")
    except FileNotFoundError as e:
        taf_logger.debug(f"No config file found, skipping PIN from env. {str(e)}")
        return None
    except InvalidConfigError as e:
        taf_logger.warning(f"Invalid config.toml, skipping PIN from env. {str(e)}")
        return None

    if public_key is None:
        taf_logger.debug("No public key provided, skipping PIN from env.")
        return None
    root_auth_repo_name = cfg.root.name
    archive_dir = taf_dir.parent
    root_auth_repo = AuthenticationRepository(path=(archive_dir / root_auth_repo_name))
    if not root_auth_repo.is_git_repository:
        taf_logger.debug(
            f"{root_auth_repo_name} is not a valid authentication repository."
        )
        return None

    raw_mapping = root_auth_repo.get_keys_mapping()
    if raw_mapping is None:
        taf_logger.debug(
            f"No keys mapping found for root auth repo {root_auth_repo}, skipping PIN from env."
        )
        return None

    return _pin_from_keys_mapping(public_key, raw_mapping)


def _pin_from_keys_mapping(public_key: SSlibKey, mapping: dict) -> Optional[str]:
    """
    Return the PIN stored in PIN_<KEY_NAME>, where <KEY_NAME> is the entry in
    keys-mapping.json that matches `public_key`. If no match or no env var,
    return None.
    """
    key_name = KeysMapping.from_dict(mapping).find_name_by_public(
        get_public_key_pem(public_key)
    )
    if key_name:
        return os.getenv(f"PIN_{to_env_var_upper(key_name)}")
    return None


@raise_yubikey_err("Cannot get public keys.")
def get_piv_public_keys_pem(serial=None) -> dict:
    """Return the public key of every occupied PIV slot on a YubiKey, in
    PEM format.

    Returns:
        Dict mapping serial number to a dict of {SLOT: public key PEM} for
        every slot that currently holds a certificate.

    Raises:
        - YubikeyError
    """
    taf_logger.debug(f"Extracting public keys from serial={serial}")
    status = get_slot_status(serial=serial)
    keys: dict = {}
    for dev_serial, slot_status in status.items():
        dev_keys = {}
        for slot, cert in slot_status.items():
            if cert is None:
                continue
            dev_keys[slot] = _public_key_pem(cert)
        keys[dev_serial] = dev_keys
    return keys


@raise_yubikey_err("Cannot get public keys in TUF format.")
def get_piv_public_keys_tuf(scheme=None, serial=None, taf_repo=None) -> dict:
    """Return the public key of every occupied PIV slot on a YubiKey, in
    TUF's key format. Keys listed in taf_repo's metadata are returned as
    listed there. RSA keys that it does not list are left out, unless scheme
    is given.

    Returns:
        Dict mapping serial number to a dict of {SLOT: SSlibKey}.

    Raises:
        - YubikeyError
    """
    taf_logger.debug(f"Extracting TUF-format public keys from serial={serial}")
    keys: dict = {}
    for dev_serial, slot_pems in get_piv_public_keys_pem(serial=serial).items():
        dev_keys = {}
        for slot, pub_key_pem in slot_pems.items():
            try:
                dev_keys[slot] = _get_slot_key(pub_key_pem, taf_repo, scheme)
            except SchemeNotSpecifiedError:
                continue
        keys[dev_serial] = dev_keys
    return keys


def _get_slot_key(public_key_pem, taf_repo, scheme) -> SSlibKey:
    """Return the key of a YubiKey slot as listed in taf_repo's metadata, or,
    if metadata does not list it, built with scheme"""
    if taf_repo is not None:
        for role in taf_repo.get_all_roles():
            for key in taf_repo.get_public_keys_of_role(role):
                if is_same_public_key(key, public_key_pem):
                    return key
    return get_sslib_key_from_value(public_key_pem, scheme)


def list_connected_yubikeys():
    """Lists all connected YubiKeys with their serial numbers and details."""
    yubikeys = list_all_devices()
    if not yubikeys:
        print("No YubiKeys connected.")
        taf_logger.debug("list_connected_yubikeys found no devices.")
    else:
        taf_logger.debug(f"list_connected_yubikeys found {len(yubikeys)} device(s).")
        for index, (_, info) in enumerate(yubikeys, start=1):
            print(f"YubiKey {index}:")
            print(f"  Serial Number: {info.serial}")
            print(f"  Version: {info.version}")
            print(f"  Form Factor: {info.form_factor}")


def _resolve_and_cache_pin(
    pin_manager,
    serial_num,
    public_key,
    taf_dir,
    key_name,
    pin_confirm,
    pin_repeat,
    key_id_pins,
    creating_new_key=False,
):
    """Resolve a YubiKey's PIN (environment variable, then interactive
    prompt/validation) and cache it in pin_manager, unless already cached."""
    if pin_manager.get_pin(serial_num) is not None:
        return
    taf_logger.debug("Attempting to load key pin from environment variables")
    pin = get_pin_from_env(public_key, serial_num, taf_dir)
    if pin is not None and not creating_new_key:
        valid_pin, retries = is_valid_pin(pin, serial_num)
        if not valid_pin:
            raise InvalidPINError(
                f"The PIN for YubiKey {serial_num} from the environment is incorrect, "
                f"{retries} retries left"
            )
    if creating_new_key:
        # skips validation against the card, unlike get_and_validate_pin below
        if pin is None:
            pin = get_pin_for(key_name, pin_confirm, pin_repeat)
    elif pin is None:
        pin = get_and_validate_pin(
            key_name,
            pin_confirm,
            pin_repeat,
            serial_num,
            key_id_pins=key_id_pins,
            public_key=public_key,
        )
    pin_manager.add_pin(serial_num, pin)


def _inserted_serials():
    """Serial numbers of the inserted YubiKeys, or None if they can't be read"""
    try:
        return get_serial_nums()
    except Exception:
        taf_logger.log("NOTICE", "No YubiKeys inserted")
        return None


def _load_device_key(
    pin_manager,
    taf_repo,
    serial_num,
    public_key,
    key_name,
    role,
    slot,
    pin_confirm,
    pin_repeat,
    key_id_pins,
    creating_new_key=False,
):
    """Get the PIN of the YubiKey holding public_key, and record the key as a
    key of role in taf_repo's YubiKey store"""
    lookup_path = taf_repo.path if taf_repo is not None else Path.cwd()
    _resolve_and_cache_pin(
        pin_manager,
        serial_num,
        public_key,
        find_taf_directory(lookup_path),
        key_name,
        pin_confirm,
        pin_repeat,
        key_id_pins,
        creating_new_key=creating_new_key,
    )
    if taf_repo is not None:
        # when reusing the same yubikey, public key will already be in the public keys dictionary
        # but the key name still needs to be added to the key id mapping dictionary
        taf_repo.yubikey_store.add_key_data(
            key_name, serial_num, public_key, role, slot=slot
        )


def _prompt_for_slot(serial_num, options):
    """Ask the user to pick one of `options` (a list of (SLOT, label) pairs,
    already ordered) and return the chosen SLOT. Auto-selects without
    prompting if there's only one option."""
    if len(options) == 1:
        slot, label = options[0]
        print(
            f"YubiKey serial={serial_num}: using the only available slot={slot.name} ({label})"
        )
        return slot
    print(f"YubiKey serial={serial_num}:")
    for index, (slot, label) in enumerate(options, start=1):
        print(f"  {index}. slot={slot.name} {label}")
    choice = click.prompt("Select a slot", type=click.IntRange(1, len(options)))
    return options[choice - 1][0]


def _prompt_for_slot_selection(serial_num, device_keys):
    """Ask the user which of a device's occupied PIV slots holds the key
    they want."""
    ordered = sorted(device_keys.items(), key=lambda item: item[0].value)
    options = [(slot, f"keyid={key.keyid}") for slot, key in ordered]
    slot = _prompt_for_slot(serial_num, options)
    return slot, device_keys[slot]


def _prompt_for_new_key_slot(serial_num, occupied_slots):
    """Pick a free PIV slot to write a newly generated key into. Raises
    YubikeyError if every setup slot is already occupied."""
    free_slots = sorted(SETUP_SLOTS - set(occupied_slots), key=lambda s: s.value)
    if not free_slots:
        raise YubikeyError(
            f"YubiKey serial={serial_num} has no free slot. taf will not "
            "overwrite or reset it - reset the YubiKey's PIV application "
            "outside of taf and try again."
        )
    options = [(slot, "free") for slot in free_slots]
    return _prompt_for_slot(serial_num, options)


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
    key_id_pins,
    scheme=None,
):
    taf_logger.debug(
        f"_read_and_check_single_yubikey for role='{role}', key_name='{key_name}', retrying={retrying}"
    )
    if retrying:
        if prompt_message is None:
            prompt_message = f"Please insert {key_name} YubiKey and press ENTER"
        getpass(prompt_message)

    if not yubikeys_to_skip:
        yubikeys_to_skip = []

    # make sure that YubiKey is inserted
    serials = _inserted_serials()
    if serials is None:
        return None
    taf_logger.debug(f"Found serials={serials} for single key check.")
    if taf_repo is None:
        # if setting up a YubiKey outside of the creation of a new repository or addition of new roles
        if len(serials) > 1:
            print("\nPlease insert only one YubiKey\n")
            taf_logger.debug("Multiple YubiKeys inserted, cannot proceed.")
            return None
    else:
        not_loaded = [
            serial
            for serial in serials
            if not taf_repo.yubikey_store.is_loaded_for_role(serial, role)
            and serial not in yubikeys_to_skip
        ]
        taf_logger.debug(f"Not loaded for role='{role}': {not_loaded}")

        if len(not_loaded) != 1:
            print("\nPlease insert only one not previously inserted YubiKey\n")
            return None

        # no need to try loading keys that we know were previously loaded
        serials = not_loaded

    serial_num = serials[0]
    # check if this key is already loaded as the provided role's key (we can use the same key
    # to sign different metadata)
    # read the public key, unless a new key needs to be generated on the yubikey
    slot = None
    if creating_new_key:
        # occupancy is an unauthenticated PIV read - resolve the slot before
        # ever asking for a PIN, and abort outright if none is free
        occupied = get_piv_public_keys_pem(serial=serial_num).get(serial_num, {})
        slot = _prompt_for_new_key_slot(serial_num, occupied.keys())
        public_key = None
    else:
        device_keys = {
            slot: _get_slot_key(public_key_pem, taf_repo, scheme)
            for slot, public_key_pem in get_piv_public_keys_pem(serial=serial_num)
            .get(serial_num, {})
            .items()
        }
        if not device_keys:
            print(
                f"YubiKey serial={serial_num} has no key set up yet - nothing to "
                "reuse. Insert a YubiKey that has already been set up, or answer "
                "'n' to create a new key instead."
            )
            return None
        elif len(device_keys) == 1:
            ((slot, public_key),) = device_keys.items()
        else:
            slot, public_key = _prompt_for_slot_selection(serial_num, device_keys)

    # check if this yubikey is can be used for signing the provided role's metadata
    # if the key was already registered as that role's key
    if not registering_new_key and role is not None and taf_repo is not None:
        if not taf_repo.is_valid_metadata_yubikey(role, public_key):
            taf_logger.debug(f"Public key not valid for role='{role}'.")
            return None

    _load_device_key(
        pin_manager,
        taf_repo,
        serial_num,
        public_key,
        key_name,
        role,
        slot,
        pin_confirm,
        pin_repeat,
        key_id_pins,
        creating_new_key=creating_new_key,
    )

    taf_logger.debug(
        f"_read_and_check_single_yubikey returning for serial={serial_num}, key_name='{key_name}'"
    )
    return public_key, serial_num, key_name, slot


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
    key_id_pins,
):
    taf_logger.debug(
        f"_read_and_check_yubikeys for role='{role}', key_names={key_names}, retrying={retrying}"
    )
    if retrying:
        if prompt_message is None:
            if not hide_threshold_message:
                threshold = taf_repo.get_role_threshold(role)
                prompt_message = f"Please insert {role} ({', '.join(key_names)}) YubiKey(s) (threshold {threshold}) and press ENTER"
            else:
                prompt_message = f"Please insert {role} ({', '.join(key_names)}) YubiKey(s) and press ENTER"
        getpass(prompt_message)

    serials = _inserted_serials()
    if serials is None:
        return None
    taf_logger.debug(f"Detected YubiKey serials={serials}")

    if not len(serials):
        taf_logger.debug("No YubiKeys present.")
        return None

    # check if this key is already loaded as the provided role's key (we can use the same key
    # to sign different metadata)
    yubikeys = []
    invalid_keys = []
    all_loaded = True

    for index, serial_num in enumerate(serials):
        if not taf_repo.yubikey_store.is_loaded_for_role(serial_num, role):
            all_loaded = False
            # a device can hold more than one key valid for this role (one
            # per slot) - collect them all instead of stopping at the first
            # match. SIGNATURE is checked first to match prior behavior.
            device_keys = get_piv_public_keys_tuf(
                serial=serial_num, taf_repo=taf_repo
            ).get(serial_num, {})
            ordered_slots = [SLOT.SIGNATURE] + [
                s for s in device_keys if s != SLOT.SIGNATURE
            ]
            found_valid_key = False
            for candidate_slot in ordered_slots:
                public_key = device_keys.get(candidate_slot)
                if public_key is None:
                    continue
                if not (
                    role is None
                    or taf_repo is None
                    or taf_repo.is_valid_metadata_yubikey(role, public_key)
                ):
                    continue
                slot = candidate_slot
                found_valid_key = True

                key_name = (
                    taf_repo.keys_name_mappings.get(public_key.keyid)
                    or f"{serial_num}-{slot.name}"
                )
                taf_logger.debug(
                    f"Potential YubiKey with serial={serial_num}, associated key_name='{key_name}', slot={slot}."
                )
                _load_device_key(
                    pin_manager,
                    taf_repo,
                    serial_num,
                    public_key,
                    key_name,
                    role,
                    slot,
                    pin_confirm,
                    pin_repeat,
                    key_id_pins,
                )
                yubikeys.append((public_key, serial_num, key_name, slot))

            if not found_valid_key:
                invalid_keys.append(serial_num)
                taf_logger.debug(f"Serial={serial_num} not valid for role='{role}'.")

    if not hide_already_loaded_message and all_loaded:
        print("All inserted YubiKeys already loaded")
        taf_logger.debug(
            f"All YubiKeys inserted were already loaded for role='{role}'."
        )

    if invalid_keys:
        taf_logger.log(
            "NOTICE",
            f"YubiKey(s) with serial(s) {', '.join(str(s) for s in invalid_keys)} "
            f"do not hold a signing key for role '{role}' and were skipped for this "
            "role - they may still be used to sign other roles in this run.",
        )

    return yubikeys


def get_piv_sign_args(public_key: SSlibKey) -> Tuple:
    """Return the key type, hash algorithm and padding for signing with the key
    of a PIV slot, from the signing scheme of its public part"""
    key_type = KEY_TYPE.from_public_key(public_key._crypto_key())
    hash_algorithm = None
    signing_padding = None
    if key_type != KEY_TYPE.ED25519:
        hash_name = public_key.get_hash_algorithm_name()
        hash_algorithm = getattr(hashes, hash_name.upper())()
    if is_rsa_scheme(public_key.scheme):
        if public_key.get_padding_name() == "pss":
            signing_padding = padding.PSS(
                mgf=padding.MGF1(hash_algorithm),
                salt_length=padding.PSS.DIGEST_LENGTH,
            )
        else:
            signing_padding = padding.PKCS1v15()
    return key_type, hash_algorithm, signing_padding


@raise_yubikey_err("Cannot sign data.")
def sign_piv(data, pin, sign_args: Tuple, serial=None, slot=SLOT.SIGNATURE):
    """Sign data with key from YubiKey's piv slot.

    Args:
        - data(bytes): Data to be signed
        - pin(str): Pin for piv slot login.
        - sign_args(tuple): Key type, hash algorithm and padding of the key,
                            from get_piv_sign_args
        - slot(SLOT): The PIV slot holding the signing key. Defaults to
                      SLOT.SIGNATURE.

    Returns:
        Signature (bytes)

    Raises:
        - YubikeyError
    """
    taf_logger.debug(f"Signing data using YubiKey serial={serial}, slot={slot}.")
    key_type, hash_algorithm, signing_padding = sign_args
    with _yk_piv_ctrl(serial=serial) as [(ctrl, _)]:
        ctrl.verify_pin(pin)
        sig = ctrl.sign(slot, key_type, data, hash_algorithm, signing_padding)
        taf_logger.debug("Data signed successfully.")
        return sig


def _get_protected_management_key(ctrl):
    """Return the management key stored in the card's PIN-protected data
    object, or None if it was never stored there. Requires the PIN to
    already be verified on this session.
    """
    try:
        key = get_pivman_protected_data(ctrl).key
        taf_logger.debug(f"Protected management key lookup found={key is not None}")
        return key
    except Exception as e:
        taf_logger.debug(f"Protected management key lookup failed: {e}")
        return None


def _slot_occupied(ctrl, slot) -> bool:
    """Check whether a PIV slot already has a key in it."""
    try:
        # detects a key even without a certificate (e.g. an interrupted setup())
        ctrl.get_slot_metadata(slot)
        return True
    except NotSupportedError:
        # firmware older than 5.3 - fall back to checking for a certificate
        pass
    except Exception:
        return False
    try:
        ctrl.get_certificate(slot)
        return True
    except Exception:
        return False


def get_slot_status(serial=None) -> dict:
    """Return the certificate (or None if empty) currently in every usable
    PIV slot of the inserted YubiKey(s).

    Returns:
        Dict mapping serial number to a dict of {SLOT: x509.Certificate | None}
        for every standard and retired slot (the attestation slot is excluded,
        since it's Yubico-reserved and not usable for taf's purposes).

    Raises:
        - YubikeyError
    """
    usable_slots = [s for s in SLOT if s != SLOT.ATTESTATION]
    with _yk_piv_ctrl(serial=serial) as sessions:
        status = {}
        for ctrl, dev_serial in sessions:
            slot_status = {}
            for slot in usable_slots:
                try:
                    slot_status[slot] = ctrl.get_certificate(slot)
                except Exception:
                    slot_status[slot] = None
            status[dev_serial] = slot_status
        return status


def is_slot_occupied(serial, slot) -> bool:
    """Check whether a PIV slot on the inserted YubiKey already has a key in
    it. See _slot_occupied for how occupancy is determined.

    Raises:
        - YubikeyError
    """
    with _yk_piv_ctrl(serial=serial) as [(ctrl, _)]:
        return _slot_occupied(ctrl, slot)


@raise_yubikey_err("Cannot setup Yubikey.")
def setup(
    pin,
    serial,
    cert_cn,
    cert_exp_days=365,
    private_key_pem=None,
    key_size=None,
    slot=SLOT.SIGNATURE,
    management_key=None,
    scheme=None,
):
    """Generate or import a key (and self-signed certificate) into a single
    PIV slot of the inserted YubiKey. Every other slot, and the PIN/PUK, are
    left untouched. Raises if the target slot is already occupied.

    Args:
        - cert_cn(str): x509 common name
        - cert_exp_days(int): x509 expiration (in days from now)
        - private_key_pem(str): Private key in PEM format. If given, it will be
                                imported to Yubikey.
        - scheme(str): Signing scheme of the generated key, which sets its type.
                       Needed when private_key_pem is not given.
        - key_size(int): Size of a generated RSA key in bits, 3072 if not
                         given.
        - slot(SLOT): The PIV slot to write the key and certificate to.
                      Defaults to SLOT.SIGNATURE.
        - management_key(bytes): The card's current management key, used to
                                 authenticate instead of looking up the
                                 stored, PIN-protected one.

    Returns:
        PIV public key in PEM format (bytes)

    Raises:
        - YubikeyError
    """
    taf_logger.debug(
        f"Initializing YubiKey setup for serial={serial}, key_size={key_size}, "
        f"cert_cn='{cert_cn}', slot={slot}"
    )
    with _yk_piv_ctrl(serial=serial) as [(ctrl, _)]:
        # checking slot occupancy is an unauthenticated PIV read - do it
        # before verifying the PIN or authenticating with the management
        # key, so an occupied slot fails fast without spending a PIN retry
        # attempt on an operation that's going to be refused anyway
        if _slot_occupied(ctrl, slot):
            raise YubikeyError(
                f"Slot {slot.name} already has a key. taf will not overwrite "
                "or reset it - reset the YubiKey's PIV application outside of "
                "taf and try again."
            )

        try:
            if management_key is not None:
                ctrl.authenticate(MANAGEMENT_KEY_TYPE.TDES, management_key)
            else:
                ctrl.verify_pin(pin)
                stored_key = _get_protected_management_key(ctrl)
                ctrl.authenticate(
                    MANAGEMENT_KEY_TYPE.TDES, stored_key or DEFAULT_MANAGEMENT_KEY
                )
        except ApduError as e:
            if e.sw == SW.SECURITY_CONDITION_NOT_SATISFIED:
                raise YubikeyError(
                    "Could not authenticate with the YubiKey's management key. "
                    "This can happen if its PIV application was previously set "
                    "up by a different tool or is in an inconsistent state - "
                    "reset it (e.g. `ykman piv reset`) and try again."
                ) from e
            raise

        if private_key_pem is None:
            taf_logger.debug(f"Generating {scheme} private key on the fly...")
            generated_pem, _ = generate_keypair(scheme, key_size)
            private_key = load_pem_private_key(generated_pem, None, default_backend())
        else:
            taf_logger.debug("Loading provided private key PEM...")
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

        key_type = KEY_TYPE.from_public_key(private_key.public_key())
        try:
            ctrl.check_key_support(
                key_type, PIN_POLICY.ALWAYS, TOUCH_POLICY.DEFAULT, generate=False
            )
        except NotSupportedError as e:
            raise YubikeyError(
                f"YubiKey serial={serial} cannot hold this key: {e}. Use a 2048-bit "
                'RSA key ("length": 2048 or --key-size 2048) or an ECDSA scheme.'
            ) from e

        taf_logger.debug(f"Placing key in {slot.name} slot with PIN_POLICY.ALWAYS...")
        ctrl.put_key(slot, private_key, PIN_POLICY.ALWAYS)
        pub_key = private_key.public_key()

        now = datetime.datetime.now()
        valid_to = now + datetime.timedelta(days=cert_exp_days)

        taf_logger.debug("Generating and importing self-signed certificate...")
        name = x509.Name([x509.NameAttribute(x509.NameOID.COMMON_NAME, cert_cn)])
        cert = (
            x509.CertificateBuilder()
            .subject_name(name)
            .issuer_name(name)
            .public_key(pub_key)
            .serial_number(x509.random_serial_number())
            .not_valid_before(now)
            .not_valid_after(valid_to)
            .sign(
                private_key,
                None if isinstance(private_key, Ed25519PrivateKey) else hashes.SHA256(),
                default_backend(),
            )
        )

        ctrl.put_certificate(slot, cert)

    taf_logger.debug("YubiKey setup complete.")
    return pub_key.public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
    )


def setup_new_yubikey(
    pin_manager: PinManager,
    serial: str,
    scheme: Optional[str] = None,
    key_size: Optional[int] = None,
    slot=SLOT.SIGNATURE,
) -> SSlibKey:
    taf_logger.debug(
        f"Starting new YubiKey setup for serial={serial}, scheme={scheme}, "
        f"key_size={key_size}, slot={slot}"
    )
    pin = pin_manager.get_pin(serial)
    cert_cn = input("Enter key holder's name: ")
    print("Generating key, please wait...")
    pub_key_pem = setup(
        pin,
        serial,
        cert_cn,
        cert_exp_days=EXPIRATION_INTERVAL,
        key_size=key_size,
        slot=slot,
        scheme=scheme,
    ).decode("utf-8")
    key = get_sslib_key_from_value(pub_key_pem, scheme)
    taf_logger.debug(
        f"New YubiKey setup complete for serial={serial}, keyid={key.keyid}"
    )
    return key


def verify_yk_inserted(serial_num, key_name):
    def _check_if_yk_inserted():
        try:
            serials = get_serial_nums()
        except Exception:
            return False

        return serial_num in serials

    while not _check_if_yk_inserted():
        prompt_message = f"Please insert {key_name} YubiKey and press ENTER"
        taf_logger.debug(f"Waiting for user to insert YubiKey serial={serial_num}")
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
    key_id_pins=None,
    scheme=None,
):
    """Prompt for YubiKey insertion, handle reading, verifying, and returning the discovered YubiKey(s).
    scheme is the signing scheme of a key that is registered but not in metadata yet, needed if it is
    an RSA key."""
    taf_logger.debug(
        f"yubikey_prompt called with role='{role}', key_names={key_names}, registering_new_key={registering_new_key}, creating_new_key={creating_new_key}"
    )
    retry_counter = 0
    yubikeys = None

    if key_id_pins is None:
        key_id_pins = {}

    while True:
        retrying = retry_counter > 0
        taf_logger.debug(
            f"YubiKey prompt iteration={retry_counter}, retrying={retrying}"
        )

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
                key_id_pins,
                scheme=scheme,
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
                key_id_pins,
            )

        if not yubikeys and not retry_on_failure:
            taf_logger.debug("No YubiKeys found and retry_on_failure=False. Returning.")
            return [(None, None, None, None)]
        if yubikeys:
            taf_logger.debug(f"Returning discovered YubiKeys: {yubikeys}")
            return yubikeys

        retry_counter += 1


def yk_secrets_handler(prompt, pin_manager, serial_num):
    taf_logger.debug(
        f"yk_secrets_handler called with prompt='{prompt}', serial_num={serial_num}"
    )
    if prompt == "pin":
        return pin_manager.get_pin(serial_num)
    raise YubikeyError(f"Invalid prompt {prompt}")


def to_env_var_upper(key_name):
    """Convert key name to uppercase and replace '-' with '_' for environment variable."""
    return key_name.upper().replace("-", "_")
