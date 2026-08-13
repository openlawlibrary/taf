from logging import DEBUG, ERROR
from typing import Dict, Optional, Tuple

from pathlib import Path
from cryptography import x509
from logdecorator import log_on_end, log_on_error, log_on_start
from taf.api.utils._conf import find_taf_directory
from taf.auth_repo import AuthenticationRepository
from taf.constants import DEFAULT_RSA_SIGNATURE_SCHEME
from taf.exceptions import KeystoreError, TAFError, YubikeyError

# from taf.constants import DEFAULT_RSA_SIGNATURE_SCHEME
from taf.log import taf_logger
from taf.tuf.keys import get_sslib_key_from_value
from taf.tuf.repository import MAIN_ROLES
import taf.yubikey.yubikey as yk
from taf.yubikey.yubikey import SETUP_SLOTS
from taf.yubikey.yubikey_manager import PinManager
from yubikit.piv import SLOT


def _ensure_slot_free(serial: str, piv_slot: SLOT) -> None:
    """Raise a clear error if the target slot is already occupied."""
    if yk.is_slot_occupied(serial, piv_slot):
        raise YubikeyError(
            f"The {piv_slot.name} slot on YubiKey {serial} already has a key. "
            "taf will not overwrite or reset it - reset the YubiKey's PIV "
            "application outside of taf and try again."
        )
    print(f"Setting up a new key in the {piv_slot.name} slot.")


def _prepare_setup(
    pin_manager: PinManager,
    piv_slot: SLOT,
    serial: Optional[str] = None,
    insert_prompt: Optional[str] = None,
) -> Tuple[str, str]:
    """Resolve which YubiKey to use, confirm the target slot is free, and get
    its PIN."""
    if serial is None:
        serial = _resolve_single_serial(insert_prompt)

    # an unauthenticated PIV read, so check it before ever asking for a PIN
    _ensure_slot_free(serial, piv_slot)

    # needed to unlock the card's stored, PIN-protected management key -
    # reuse the same resolve-from-env-then-validate flow used everywhere
    # else a PIN is entered, instead of a partial reimplementation
    name = f"YubiKey {serial}" if len(yk.get_serial_nums()) > 1 else "YubiKey"
    taf_dir = find_taf_directory(Path.cwd())
    yk._resolve_and_cache_pin(
        pin_manager, serial, None, taf_dir, name, True, True, None
    )

    return serial, pin_manager.get_pin(serial)


def _resolve_single_serial(prompt: Optional[str] = None) -> str:
    """Find the currently inserted YubiKey's serial number, raising if none
    or more than one is inserted."""
    if prompt is not None:
        input(prompt)
    serials = yk.get_serial_nums()
    if not len(serials):
        raise YubikeyError("YubiKey not inserted")
    if len(serials) > 1:
        raise YubikeyError("More than one YubiKey is inserted. Please insert only one")
    return serials[0]


def _resolve_slot(slot: str) -> SLOT:
    try:
        piv_slot = SLOT[slot.upper()]
    except KeyError:
        raise YubikeyError(f"'{slot}' is not a valid YubiKey PIV slot name")
    if piv_slot not in SETUP_SLOTS:
        raise YubikeyError(
            f"'{slot}' is not a supported slot for key setup. Choose one of: "
            + ", ".join(s.name for s in SETUP_SLOTS)
        )
    return piv_slot


@log_on_start(DEBUG, "Exporting public pem from YubiKey", logger=taf_logger)
@log_on_end(DEBUG, "Exported public pem from YubuKey", logger=taf_logger)
@log_on_error(
    ERROR,
    "An error occurred while exporting public pem from YubiKey: {e}",
    logger=taf_logger,
    on_exceptions=TAFError,
    reraise=True,
)
def export_yk_public_pem(
    path: Optional[str] = None, serial: Optional[str] = None
) -> None:
    """
    Export public key from a YubiKey and save it to a file or print to console.

    Arguments:
        path (optional): Path to a file to which the public key should be written.
        The key is printed to console if file path is not provided.

    Side Effects:
       Write public key to a file if path is specified

    Returns:
        None
    """
    try:
        serials = [serial] if serial else yk.get_serial_nums()

        if not len(serials):
            print("YubiKey not inserted.")
            return

        for serial in serials:
            pub_key = yk.get_piv_public_key_tuf(serial=serial)
            keyid = yk._get_legacy_keyid(pub_key)
            pub_key_pem = pub_key.keyval["public"]
            if path is None:
                print(f"Serial: {serial}")
                print(f"Key id: {keyid}")
                print(pub_key_pem)
            else:
                if not path.endswith(".pub"):
                    path = f"{path}.pub"
                pem_path = Path(path)
                parent = pem_path.parent
                parent.mkdir(parents=True, exist_ok=True)
                pem_path.write_text(pub_key_pem)
    except Exception:
        print("Could not export the public key. Check if a YubiKey is inserted")
        return


@log_on_start(DEBUG, "Exporting certificate from YubiKey", logger=taf_logger)
@log_on_end(DEBUG, "Exported certificate from YubuKey", logger=taf_logger)
@log_on_error(
    ERROR,
    "An error occurred while exporting certificate from YubiKey: {e}",
    logger=taf_logger,
    on_exceptions=TAFError,
    reraise=True,
)
def export_yk_certificate(
    path: Optional[str] = None, serial: Optional[str] = None
) -> None:
    """
    Export certificate from the YubiKey.

    Arguments:
        path (optional): Path to a file to which the certificate key should be written.
        Will be written to the user's home directory by default

    Side Effects:
       Write certificate to a file

    Returns:
        None
    """
    try:
        serials = [serial] if serial else yk.get_serial_nums()

        if not len(serials):
            print("YubiKey not inserted.")
            return
        for serial in serials:
            pub_key_pem = yk.export_piv_pub_key(serial=serial).decode("utf-8")
            scheme = DEFAULT_RSA_SIGNATURE_SCHEME
            key = get_sslib_key_from_value(pub_key_pem, scheme)
            yk.export_yk_certificate(path, key, serial)
    except Exception as e:
        print(e)
        print("Could not export certificate. Check if a YubiKey is inserted")
        return


@log_on_start(DEBUG, "Listing roles of inserted YubiKesy", logger=taf_logger)
@log_on_error(
    ERROR,
    "An error occurred while listing roles of inserted YubiKeys: {e}",
    logger=taf_logger,
    on_exceptions=TAFError,
    reraise=True,
)
def get_yk_roles(path: str, serial: Optional[str] = None) -> Dict:
    """
    List all roles that the inserted YubiKey whose metadata files can be signed by this YubiKey.
    Every occupied PIV slot is checked. In case of delegated targets roles, include the
    delegation paths.

    Arguments:
        path: Authentication repository's path.
    Side Effects:
        None

    Returns:
        A dictionary containing roles and delegated paths in case of delegated target roles
    """
    serials = [serial] if serial else yk.get_serial_nums()
    roles_per_yubikes: Dict = {}

    if not len(serials):
        print("YubiKey not inserted.")
        return roles_per_yubikes

    auth = AuthenticationRepository(path=path)
    for serial in serials:
        roles_with_paths: Dict = {}
        keys = yk.get_piv_public_keys_tuf(serial=serial).get(serial, {})
        for pub_key in keys.values():
            for role in auth.find_associated_roles_of_key(pub_key):
                if role in roles_with_paths:
                    continue
                roles_with_paths[role] = (
                    {} if role in MAIN_ROLES else auth.get_role_paths(role)
                )
        roles_per_yubikes[serial] = roles_with_paths
    return roles_per_yubikes


@log_on_start(DEBUG, "Listing YubiKey PIV slot status", logger=taf_logger)
@log_on_error(
    ERROR,
    "An error occurred while listing YubiKey PIV slots: {e}",
    logger=taf_logger,
    on_exceptions=TAFError,
    reraise=True,
)
def list_yk_slots(serial: Optional[str] = None) -> None:
    """
    Print the free/occupied status of every PIV slot taf can set a key up
    in on the inserted YubiKey(s), including the holder name and expiry of
    any certificate found. Retired slots are excluded, since taf doesn't
    offer them as a setup target (see SETUP_SLOTS).

    Arguments:
        serial (optional): Serial number of a specific YubiKey. Lists slots
            for every inserted YubiKey if not specified.

    Side Effects:
        None

    Returns:
        None
    """
    serials = [serial] if serial else yk.get_serial_nums()
    if not len(serials):
        print("YubiKey not inserted.")
        return

    for dev_serial in serials:
        slot_status = yk.get_slot_status(serial=dev_serial)[dev_serial]
        print(f"\nSerial: {dev_serial}")
        for slot, cert in slot_status.items():
            if slot not in SETUP_SLOTS:
                continue
            if cert is None:
                print(f"  {slot.name:<15} free")
            else:
                cn = ""
                attrs = cert.subject.get_attributes_for_oid(x509.OID_COMMON_NAME)
                if attrs:
                    cn = attrs[0].value
                expires = cert.not_valid_after_utc.strftime("%Y-%m-%d")
                print(f"  {slot.name:<15} occupied   {cn}   expires {expires}")


@log_on_start(DEBUG, "Setting up a new signing YubiKey", logger=taf_logger)
@log_on_end(DEBUG, "Finished setting up a new signing YubiKey", logger=taf_logger)
@log_on_error(
    ERROR,
    "An error occurred while setting up a new YubiKey: {e}",
    logger=taf_logger,
    on_exceptions=TAFError,
    reraise=True,
)
def setup_signing_yubikey(
    pin_manager: PinManager,
    certs_dir: Optional[str] = None,
    key_size: int = 2048,
    slot: str = "SIGNATURE",
) -> None:
    """
    Generate a new key and copy it to the given PIV slot of the inserted YubiKey.
    Optionally export and save the certificate to a file.

    Arguments:
        certs_dir (optional): Path to a directory where the exported certificate should be stored.
        slot (optional): Name of the PIV slot to set the key up in ("SIGNATURE",
            "AUTHENTICATION", "KEY_MANAGEMENT", or "CARD_AUTH"). Defaults to "SIGNATURE".

    Side Effects:
       None

    Returns:
        None
    """
    piv_slot = _resolve_slot(slot)

    serial_num, _ = _prepare_setup(
        pin_manager,
        piv_slot,
        insert_prompt="Insert the YubiKey you want to set up and press ENTER",
    )

    key = yk.setup_new_yubikey(
        pin_manager,
        serial_num,
        key_size=key_size,
        slot=piv_slot,
    )
    yk.export_yk_certificate(certs_dir, key, serial_num, slot=piv_slot)


@log_on_start(DEBUG, "Setting up a new test YubiKey", logger=taf_logger)
@log_on_end(DEBUG, "Finished setting up a test YubiKey", logger=taf_logger)
@log_on_error(
    ERROR,
    "An error occurred while setting up a test YubiKey: {e}",
    logger=taf_logger,
    on_exceptions=TAFError,
)
def setup_test_yubikey(
    pin_manager: PinManager,
    key_path: str,
    key_size: Optional[int] = 2048,
    serial: Optional[str] = None,
    slot: str = "SIGNATURE",
) -> None:
    """
    Copy the specified key to the inserted YubiKey's given PIV slot.

    Arguments:
        key_path: Path to a key which should be copied to a YubiKey.
        slot (optional): Name of the PIV slot to copy the key into ("SIGNATURE",
            "AUTHENTICATION", "KEY_MANAGEMENT", or "CARD_AUTH"). Defaults to "SIGNATURE".

    Side Effects:
       None

    Returns:
        None
    """
    key_pem_path = Path(key_path)
    if not key_pem_path.is_file():
        raise KeystoreError(f"{key_pem_path} does not exist")
    key_pem = key_pem_path.read_bytes()

    piv_slot = _resolve_slot(slot)
    serial, pin = _prepare_setup(pin_manager, piv_slot, serial=serial)

    print(f"Importing RSA private key from {key_path} to Yubikey...")
    pub_key = yk.setup(
        pin,
        serial,
        "Test Yubikey",
        private_key_pem=key_pem,
        key_size=key_size,
        slot=piv_slot,
    )
    print("\nPrivate key successfully imported.\n")
    print("\nPublic key (PEM): \n{}".format(pub_key.decode("utf-8")))
