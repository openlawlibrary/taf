"""YubiKeys: their signer and private key URIs, loading signers from them,
and setting up the keys of new roles on them."""

from functools import partial
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union
from urllib import parse

import click
from securesystemslib.signer import (
    SIGNER_FOR_URI_SCHEME,
    SSlibKey,
    Signer,
    SecretsHandler,
    Signature,
)

from taf import YubikeyMissingLibrary
from taf.auth_repo import AuthenticationRepository
from taf.exceptions import SigningError, YubikeyError
from taf.log import taf_logger
from taf.models.types import Role, UserKeyData
from taf.signers.base import InputNeeded, KeyStorage, load_signer
from taf.tuf.keys import _get_legacy_keyid, get_sslib_key_from_value
from taf.tuf.repository import is_auth_repo

try:
    import taf.yubikey.yubikey as yk
except ImportError:
    taf_logger.warning(
        "WARNING: yubikey-manager dependency not installed. You will not be able to use YubiKeys."
    )
    yk = YubikeyMissingLibrary()  # type: ignore


class YkSigner(Signer):
    """Signer implementation for Yubikeys.

    Provides a minimal compatibility layer over `taf.yubikey` module functions
    for use with MetadataRepository.

    Attrs:
        public_key: An SSlibkey, whose keyid and signing scheme are the single
                of truth for creating signatures.
        pin_handler: A function, which is called in `sign` and expected to
                return the Yubikey pin.
    """

    # prefix of YubiKey private key URIs
    SCHEME = "yk"
    _SECRET_PROMPT = "pin"  # nosec B105

    def __init__(
        self,
        public_key: SSlibKey,
        serial_num: int,
        pin_handler: SecretsHandler,
        key_name: str,
        slot=None,
    ):

        self._public_key = public_key
        self._pin_handler = pin_handler
        self._serial_num = serial_num
        self._key_name = key_name
        # the PIV slot holding this key; None defaults to SLOT.SIGNATURE in
        # sign() - kept untyped here so this module stays importable without
        # yubikey-manager installed (an optional extra)
        self._slot = slot
        self._sign_args = yk.get_piv_sign_args(public_key)

    @property
    def public_key(self) -> SSlibKey:
        return self._public_key

    @property
    def serial_num(self) -> int:
        return self._serial_num

    @property
    def key_name(self) -> str:
        return self._key_name

    @property
    def slot(self):
        return self._slot

    def sign(self, payload: bytes) -> Signature:
        pin = self._pin_handler(self._SECRET_PROMPT)
        yk.verify_yk_inserted(self.serial_num, self.key_name)
        slot = self._slot if self._slot is not None else yk.SLOT.SIGNATURE
        sig = yk.sign_piv(
            payload, pin, self._sign_args, serial=self.serial_num, slot=slot
        )
        return Signature(self.public_key.keyid, sig.hex())

    @classmethod
    def from_priv_key_uri(
        cls,
        priv_key_uri: str,
        public_key: SSlibKey,
        secrets_handler: Optional[SecretsHandler] = None,
    ) -> "Signer":
        """URI format: ``yk:<serial>?slot=<hex PIV slot>&name=<key name>``.
        Slot and name are optional."""
        uri = parse.urlparse(priv_key_uri)
        if uri.scheme != cls.SCHEME:
            raise ValueError(f"YkSigner does not support {priv_key_uri}")
        if secrets_handler is None:
            raise ValueError("YkSigner requires a secrets handler for the PIN")
        params = dict(parse.parse_qsl(uri.query))
        slot = None
        if "slot" in params:
            slot = yk.SLOT(int(params["slot"], 16))
        serial_num = int(uri.path)
        return cls(
            public_key,
            serial_num,
            secrets_handler,
            key_name=params.get("name", str(serial_num)),
            slot=slot,
        )


SIGNER_FOR_URI_SCHEME[YkSigner.SCHEME] = YkSigner


class YubiKeyStorage(KeyStorage):
    """YubiKeys. If insert is True, asks the user to insert
    them, otherwise only reads the ones that are already inserted. Sets up the
    keys of a new role on YubiKeys, or reuses keys that are already on them.
    yubikeys_data holds the keys description's YubiKeys, by name."""

    name = "YubiKey"

    def __init__(
        self,
        taf_repo: AuthenticationRepository,
        insert: bool,
        key_id_pins: Optional[Dict] = None,
        certs_dir: Optional[Union[Path, str]] = None,
        yubikeys_data: Optional[Dict[str, UserKeyData]] = None,
    ):
        self.taf_repo = taf_repo
        self.insert = insert
        self.key_id_pins = key_id_pins
        self.certs_dir = certs_dir
        self.yubikeys_data = yubikeys_data
        self.priority = 20 if insert else 10
        self.input_needed = InputNeeded.DEVICE if insert else InputNeeded.SECRET
        self.repeat = insert

    def load_signers(
        self, role: str, keys: List[SSlibKey], threshold_reached: bool
    ) -> List[Signer]:
        key_names = [
            self.taf_repo.keys_name_mappings.get(key.keyid, key.keyid) for key in keys
        ]
        signers, _ = _load_yubikeys(
            taf_repo=self.taf_repo,
            role=role,
            key_names=key_names,
            retry_on_failure=self.insert,
            hide_threshold_message=threshold_reached,
            key_id_pins=self.key_id_pins,
        )
        return signers

    def setup_keys(self, role: Role) -> Tuple[List[Signer], List[SSlibKey]]:
        yubikey_ids = role.yubikey_ids
        if yubikey_ids is None:
            yubikey_ids = []
        users_yubikeys_details = self.yubikeys_data
        if users_yubikeys_details is None:
            users_yubikeys_details = {}

        if yubikey_ids:
            if self.taf_repo.keys_name_mappings:
                # check if some of the listed key names are already defined as signing keys
                # in that case, they need to be loaded and verified
                if is_auth_repo(self.taf_repo.path):
                    existing_key_names = {
                        existing_key_name: existing_key_id
                        for existing_key_id, existing_key_name in self.taf_repo.keys_name_mappings.items()
                    }
                    for key_name in yubikey_ids:
                        if key_name in existing_key_names:
                            public_key_pem, scheme = (
                                self.taf_repo.get_public_key_of_keyid(
                                    existing_key_names[key_name]
                                )
                            )
                            key_data = {"public": public_key_pem, "scheme": scheme}
                            users_yubikeys_details[key_name] = UserKeyData(**key_data)

        taf_logger.debug(
            f"Setting up YubiKey-based role '{role.name}' requiring {role.number} key(s)."
        )
        yubikey_keys, yubikey_signers = _setup_yubikey_roles_keys(
            self.taf_repo,
            yubikey_ids,
            users_yubikeys_details,
            role,
            self.certs_dir,
            role.length,
        )
        return yubikey_signers, yubikey_keys


def get_yubikey_uri(serial_num: int, slot: Optional[int], key_name: str) -> str:
    params = {"name": key_name}
    if slot is not None:
        params["slot"] = f"{int(slot):x}"
    return f"{YkSigner.SCHEME}:{serial_num}?{parse.urlencode(params)}"


def _create_signer(auth_repo, public_key, serial_num, key_name, slot=None):
    return load_signer(
        get_yubikey_uri(serial_num, slot, key_name),
        [public_key],
        partial(
            yk.yk_secrets_handler,
            pin_manager=auth_repo.pin_manager,
            serial_num=serial_num,
        ),
    )


def _load_and_verify_yubikey(
    role_name: str,
    key_name: str,
    public_key,
    taf_repo: AuthenticationRepository,
) -> Optional[Tuple[str, object]]:
    if not click.confirm(f"Sign using {key_name} Yubikey?"):
        return None
    while True:
        yubikeys = yk.yubikey_prompt(
            [key_name],
            role=role_name,
            pin_manager=taf_repo.pin_manager,
            taf_repo=taf_repo,
            registering_new_key=True,
            creating_new_key=False,
            scheme=public_key.scheme,
            pin_confirm=True,
            pin_repeat=True,
        )
        if yubikeys:
            yk_public_key, serial_num, _, slot = yubikeys[0]
            yk_pub_key_id = yk_public_key.keyid if yk_public_key is not None else None
            if yk_pub_key_id != public_key.keyid:
                print(
                    "Public key of the inserted key is not equal to the specified one."
                )
                if not click.confirm("Try again?"):
                    return None
                continue
            return serial_num, slot


def _load_remaining_keys_of_role(
    auth_repo: AuthenticationRepository,
    role: Role,
    loaded_keys_num: int,
    users_yubikeys_details: UserKeyData,
    yk_with_public_key: Dict,
    yubikey_keys,
    signers: List,
):
    """
    If a yubikey's public key was specified, meaning that it can be added as a
    verification key without being inserted, but the total number of signing
    keys is smaller than the threshold
    """
    taf_logger.debug(
        f"{loaded_keys_num} key(s) loaded so far for role '{role.name}' (threshold {role.threshold}). "
        f"Attempting to load more with known YubiKeys."
    )
    while loaded_keys_num < role.threshold:
        loaded_keys = []
        for key_name, public_key in yk_with_public_key.items():
            result = _load_and_verify_yubikey(
                role.name,
                key_name,
                public_key,
                taf_repo=auth_repo,
            )
            if result:
                serial_num, slot = result
                loaded_keys_num += 1
                loaded_keys.append(key_name)
                signer = _create_signer(
                    auth_repo, public_key, serial_num, key_name, slot=slot
                )
                signers.append(signer)
                yubikey_keys.remove(signer.public_key)

        if loaded_keys_num < role.threshold:
            if not click.confirm(
                f"Threshold of signing keys of role {role.name} not reached. Continue?"
            ):
                raise SigningError("Not enough signing keys")
            for key_name in loaded_keys:
                yk_with_public_key.pop(key_name)


def _load_yubikeys(
    taf_repo: AuthenticationRepository,
    role: str,
    key_names: List[str],
    retry_on_failure: bool,
    hide_threshold_message: bool,
    key_id_pins: Optional[Dict] = None,
):
    """
    Loads YubiKeys for a specified role using given key names and manages the interaction process.

    Returns:
        A tuple containing two elements:
            - list of YkSigner instances representing the signers initialized from the loaded YubiKeys.
            - list of key names that were successfully loaded.
    """
    taf_logger.debug(
        f"Attempting to load YubiKeys for role '{role}' with key names: {key_names}"
    )

    signers_yubikeys: List = []
    yubikeys = yk.yubikey_prompt(
        key_names=key_names,
        pin_manager=taf_repo.pin_manager,
        role=role,
        taf_repo=taf_repo,
        retry_on_failure=retry_on_failure,
        hide_already_loaded_message=True,
        hide_threshold_message=hide_threshold_message,
        key_id_pins=key_id_pins,
    )
    taf_logger.debug(
        f"yubikey_prompt returned: {yubikeys if yubikeys else 'No YubiKeys loaded'}"
    )

    loaded_keyids = [signer.public_key.keyid for signer in signers_yubikeys]
    taf_logger.debug(f"Currently loaded keyids for {role}: {loaded_keyids}")

    loaded_key_names = []
    for public_key, serial_num, key_name, slot in yubikeys:
        if public_key is not None and public_key.keyid not in loaded_keyids:
            taf_logger.debug(
                f"Found YubiKey: Serial={serial_num}, key_name='{key_name}', keyid={public_key.keyid}, slot={slot}"
            )
            signer = _create_signer(taf_repo, public_key, serial_num, key_name, slot)
            signers_yubikeys.append(signer)
            loaded_keyids.append(public_key.keyid)
            loaded_key_names.append(key_name)
            taf_logger.info(f"Successfully loaded {key_name} from inserted YubiKey")

    return signers_yubikeys, loaded_key_names


def _setup_yubikey(
    auth_repo: AuthenticationRepository,
    role_name: str,
    key_name: str,
    scheme: Optional[str] = None,
    certs_dir: Optional[Union[Path, str]] = None,
    key_size: Optional[int] = None,
    yubikeys_to_skip: Optional[List] = None,
) -> Tuple[SSlibKey, str, object]:
    print(f"Registering keys for {key_name}")
    taf_logger.debug(
        f"Starting YubiKey setup for role '{role_name}', key '{key_name}'. Checking if user wants to reuse an existing key."
    )
    while True:
        use_existing = click.confirm("Do you want to reuse already set up Yubikey?")
        taf_logger.debug(
            f"User chose to {'reuse' if use_existing else 'generate a new'} YubiKey for '{key_name}'."
        )
        if not use_existing and not scheme:
            raise YubikeyError(
                f"Cannot set up a new key for {key_name}: set the signing scheme of {role_name}"
            )

        yubikeys = yk.yubikey_prompt(
            [key_name],
            pin_manager=auth_repo.pin_manager,
            role=role_name,
            taf_repo=auth_repo,
            registering_new_key=True,
            creating_new_key=not use_existing,
            pin_confirm=True,
            pin_repeat=True,
            yubikeys_to_skip=yubikeys_to_skip,
            scheme=scheme,
        )
        if yubikeys is not None:
            key, serial_num, key_name, slot = yubikeys[0]
            if not use_existing:
                key = yk.setup_new_yubikey(
                    auth_repo.pin_manager,
                    serial_num,
                    scheme,
                    key_size=key_size,
                    slot=slot,
                )
                # the key didn't exist yet when yubikey_prompt recorded this
                # entry, so it was stored with public_key=None - refresh it
                # now that the key has actually been generated
                auth_repo.yubikey_store.add_key_data(
                    key_name, serial_num, key, role_name, slot=slot
                )

            if certs_dir is not None:
                # check if already exported
                if len(auth_repo.yubikey_store.get_roles_of_key(serial_num, key)) == 1:
                    # this is the first time that this key is being used (can only be used once per role)
                    yk.export_yk_certificate(
                        certs_dir, key, serial=serial_num, slot=slot
                    )
            return key, serial_num, slot


def _setup_yubikey_roles_keys(
    auth_repo, yubikey_ids, users_yubikeys_details, role, certs_dir, key_size
):
    loaded_keys_num = 0
    yk_with_public_key = {}
    yubikey_keys = []
    signers = []

    # if a key was already loaded (while setting up a different role)
    # register signers and remove the key id, so that the user is not asked to enter it again
    yubikes_to_skip = []
    names_defined = bool(yubikey_ids)
    if names_defined:
        for key_name in list(yubikey_ids):
            key_data = auth_repo.yubikey_store.get_key_data(key_name)
            if key_data is not None:
                public_key, serial_num, slot = key_data
                auth_repo.yubikey_store.add_key_data(
                    key_name, serial_num, public_key, role.name, slot=slot
                )
                yubikey_ids.remove(key_name)
                yubikey_keys.append(public_key)
                loaded_keys_num += 1
                signer = _create_signer(
                    auth_repo, public_key, serial_num, key_name, slot=slot
                )
                signers.append(signer)

        # if key already loaded while setting up a different role, skip it
        # if the current role's yubikey ids are defined
        # however, if the current role's yubikey ids are not specified
        # it can be possible to reuse a yubikey
        for key_name, key_data in auth_repo.yubikey_store.yubikeys_data.items():
            if key_name not in yubikey_ids:
                yubikes_to_skip.append(key_data["serial"])
    else:
        yubikey_ids = [f"{role.name}{counter}" for counter in range(1, role.number + 1)]

    for key_name in yubikey_ids:
        public_key_text = None
        if key_name in users_yubikeys_details:
            public_key_text = users_yubikeys_details[key_name].public
        if public_key_text:
            scheme = users_yubikeys_details[key_name].scheme
            public_key = get_sslib_key_from_value(public_key_text, scheme)
            # Check if the signing key is already loaded
            if not auth_repo.yubikey_store.is_key_name_loaded(key_name):
                yk_with_public_key[key_name] = public_key
            else:
                _, serial_num, slot = auth_repo.yubikey_store.get_key_data(key_name)
                auth_repo.yubikey_store.add_key_data(
                    key_name, serial_num, public_key, role.name, slot=slot
                )
                loaded_keys_num += 1
            yubikey_keys.append(public_key)
        else:
            key_scheme = None
            if key_name in users_yubikeys_details:
                key_scheme = users_yubikeys_details[key_name].scheme
            key_scheme = key_scheme or role.scheme
            taf_logger.debug(
                f"Preparing to set up YubiKey for role '{role.name}', key_name='{key_name}'."
            )
            public_key, serial_num, slot = _setup_yubikey(
                auth_repo,
                role.name,
                key_name,
                key_scheme,
                certs_dir,
                key_size,
                yubikes_to_skip,
            )
            loaded_keys_num += 1
            signer = _create_signer(
                auth_repo, public_key, serial_num, key_name, slot=slot
            )
            signers.append(signer)

        key_id = _get_legacy_keyid(public_key)
        auth_repo.add_key_name(key_name, key_id, overwrite=names_defined)

    if loaded_keys_num < role.number:
        if loaded_keys_num < role.threshold:
            print(f"Threshold of role {role.name} is {role.threshold}")
        taf_logger.debug(
            f"Only loaded {loaded_keys_num} out of {role.number} needed key(s) for '{role.name}'. Checking if threshold is met..."
        )

        _load_remaining_keys_of_role(
            auth_repo,
            role,
            loaded_keys_num,
            users_yubikeys_details,
            yk_with_public_key,
            yubikey_keys,
            signers,
        )
    return yubikey_keys, signers
