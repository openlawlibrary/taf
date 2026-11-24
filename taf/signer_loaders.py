"""Load the signers of a role from the places that can hold its keys.

Each place, like keystore files, YubiKeys or an HSM, has its own loader.
load_role_signers tries the loaders in order of their priority, and a loader's
setup_keys loads or creates the keys of a new role, so a new place to keep keys
only needs a new loader.
"""

import click
from abc import ABC, abstractmethod
from enum import IntEnum
from functools import partial
from logging import INFO
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union

from logdecorator import log_on_start
from securesystemslib.signer import Signer, SSlibKey

from taf import YubikeyMissingLibrary
from taf.api.utils._conf import find_keystore
from taf.auth_repo import AuthenticationRepository
from taf.exceptions import KeystoreError, SigningError, YubikeyError
from taf.keystore import (
    get_key_name,
    get_keystore_keys_of_role,
    load_signer_from_keystore_uri,
    load_signer_from_private_keystore,
)
from taf.log import taf_logger
from taf.models.types import Role, UserKeyData
from taf.tuf.keys import (
    _get_legacy_keyid,
    generate_and_write_keypair,
    get_sslib_key_from_value,
)
from taf.tuf.repository import is_auth_repo
from taf.tuf.signer_uris import (
    check_keystore_path_usable_in_uri,
    get_yubikey_uri,
    load_signer,
)
from taf.utils import secret_yes_no_prompt

try:
    import taf.yubikey.yubikey as yk
except ImportError:
    taf_logger.warning(
        "WARNING: yubikey-manager dependency not installed. You will not be able to use YubiKeys."
    )
    yk = YubikeyMissingLibrary()  # type: ignore


class InputNeeded(IntEnum):
    """What a loader needs from the user"""

    # e.g. keystore files
    NONE = 0
    # e.g. the PIN of a YubiKey that is already inserted
    SECRET = 1
    # the user has to insert a device
    DEVICE = 2


class SignerLoader(ABC):
    """Loads signers of a role's keys from one place that can hold them"""

    # used in prompts, e.g. "Sign targets using YubiKey(s)?"
    name: str = ""
    # loaders with a lower priority are tried first
    priority: int = 0
    input_needed: InputNeeded = InputNeeded.NONE
    # if True, load is called again while it finds new signers
    repeat: bool = False

    @abstractmethod
    def load(
        self, role: str, keys: List[SSlibKey], threshold_reached: bool
    ) -> List[Signer]:
        """Return signers for any of keys, which are the role's keys that are
        not loaded yet"""

    @abstractmethod
    def setup_keys(self, role: Role) -> Tuple[List[Signer], List[SSlibKey]]:
        """Load or create the keys of a role that is not in metadata yet.
        Return signers of the keys that were loaded, and public keys of the
        role's other keys"""


class KeystoreSignerLoader(SignerLoader):
    """Loads signers from the role's keystore files, e.g. targets1 and targets2.
    Generates the keystore files of a new role that can't be loaded, if the
    user wants that."""

    name = "keystore"
    priority = 0
    input_needed = InputNeeded.NONE

    def __init__(
        self,
        taf_repo: AuthenticationRepository,
        keystore_path: Optional[Path],
        skip_prompt: Optional[bool] = False,
    ):
        self.taf_repo = taf_repo
        self.keystore_path = keystore_path
        self.skip_prompt = skip_prompt

    def load(
        self, role: str, keys: List[SSlibKey], threshold_reached: bool
    ) -> List[Signer]:
        if self.keystore_path is None:
            return []
        signers: List[Signer] = []
        key_names = sorted(get_keystore_keys_of_role(str(self.keystore_path), role))
        for key_name in key_names:
            loaded_keyids = [signer.public_key.keyid for signer in signers]
            missing_keys = [key for key in keys if key.keyid not in loaded_keyids]
            if not missing_keys:
                break
            signer = _load_signer_from_keystore(
                self.keystore_path, key_name, missing_keys
            )
            if signer is not None:
                signers.append(signer)
        return signers

    def setup_keys(self, role: Role) -> Tuple[List[Signer], List[SSlibKey]]:
        if self.keystore_path is None:
            taf_logger.error("No keystore provided and no default keystore found")
            raise KeyError("No keystore provided and no default keystore found")
        signers = []
        for key_num in range(role.number):
            key_name = get_key_name(role.name, key_num, role.number)
            signer, key_id = _setup_keystore_key(
                self.keystore_path,
                role.name,
                key_name,
                role.scheme,
                role.length,
                skip_prompt=self.skip_prompt,
            )
            signers.append(signer)
            self.taf_repo.add_key_name(key_name, key_id)
        return signers, []


class YubiKeySignerLoader(SignerLoader):
    """Loads signers from YubiKeys. If insert is True, asks the user to insert
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

    def load(
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


class HSMSignerLoader(SignerLoader):
    """Loads signers of keys stored on an HSM. Needs the taf[hsm] extra. Not
    implemented yet, so load_signers does not use it."""

    name = "HSM"
    priority = 30
    input_needed = InputNeeded.DEVICE

    def load(
        self, role: str, keys: List[SSlibKey], threshold_reached: bool
    ) -> List[Signer]:
        raise NotImplementedError("Loading signers from an HSM is not supported yet")

    def setup_keys(self, role: Role) -> Tuple[List[Signer], List[SSlibKey]]:
        raise NotImplementedError("Setting up keys on an HSM is not supported yet")


@log_on_start(INFO, "Loading signing keys of '{role:s}'", logger=taf_logger)
def load_signers(
    taf_repo: AuthenticationRepository,
    role: str,
    keystore: Optional[str] = None,
    key_id_pins: Optional[Dict] = None,
    use_yubikeys_to_sign: bool = False,
) -> List[Signer]:
    """
    Load role's signing keys. Make sure that at least the threshold of keys was
    loaded, but allow loading more keys (so that a metadata file can be signed
    by all of the role's keys if the user wants that)
    """
    if keystore is None:
        keystore_path = find_keystore(taf_repo.path)
        if keystore_path is None:
            taf_logger.warning("No keystore provided and no default keystore found")
        else:
            keystore = str(keystore_path)

    keystore_path = Path(keystore).expanduser().resolve() if keystore else None

    taf_repo.add_default_names_of_role(role)
    loaders: List[SignerLoader] = [
        KeystoreSignerLoader(taf_repo, keystore_path),
        YubiKeySignerLoader(taf_repo, insert=False, key_id_pins=key_id_pins),
        YubiKeySignerLoader(taf_repo, insert=True, key_id_pins=key_id_pins),
    ]
    return load_role_signers(
        taf_repo, role, loaders, ask_before_input=not use_yubikeys_to_sign
    )


def load_role_signers(
    taf_repo,
    role: str,
    loaders: List[SignerLoader],
    ask_before_input: bool = True,
) -> List[Signer]:
    """
    Load signers of a role, trying the loaders in order of their priority.
    Loaders that need no input load every key they can. The others are used
    until the threshold of signers is reached, and after that only if the user
    wants to load more keys. Before the first loader that needs a device is
    used, the user is asked if they want to sign with it, unless
    ask_before_input is False.
    """
    keys = taf_repo.get_public_keys_of_role(role)
    threshold = taf_repo.get_role_threshold(role)
    signers: Dict[str, Signer] = {}
    used_loaders = set()
    used_input = False

    def _missing_keys():
        return [key for key in keys if key.keyid not in signers]

    for loader in sorted(loaders, key=lambda loader: loader.priority):
        while _missing_keys():
            threshold_reached = len(signers) >= threshold
            if loader.input_needed != InputNeeded.NONE and threshold_reached:
                if not _load_more_keys(
                    taf_repo, role, used_input or not ask_before_input
                ):
                    return list(signers.values())
            if (
                loader.input_needed == InputNeeded.DEVICE
                and ask_before_input
                and loader.name not in used_loaders
                and not click.confirm(f"Sign {role} using {loader.name}(s)?")
            ):
                break

            missing_keyids = {key.keyid for key in _missing_keys()}
            new_signers = [
                signer
                for signer in loader.load(role, _missing_keys(), threshold_reached)
                if signer.public_key.keyid in missing_keyids
            ]
            for signer in new_signers:
                signers[signer.public_key.keyid] = signer
            if new_signers:
                used_loaders.add(loader.name)
                used_input = used_input or loader.input_needed != InputNeeded.NONE
            if not new_signers or not loader.repeat:
                break

    if len(signers) < threshold:
        raise SigningError(f"Cannot load keys of role {role}")
    return list(signers.values())


def _load_more_keys(taf_repo, role: str, may_ask: bool) -> bool:
    if not may_ask or taf_repo.pin_manager.auto_continue:
        return False
    return secret_yes_no_prompt(
        f"Threshold of {role} keys reached. "
        f"Do you want to load more {role} keys? [y/N]"
    )


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


def _load_signer_from_keystore(
    keystore_path, key_name, public_keys: List[SSlibKey]
) -> Optional[Signer]:
    if keystore_path is None:
        return None
    if (keystore_path / key_name).is_file():
        check_keystore_path_usable_in_uri(keystore_path / key_name)
        try:
            return load_signer_from_keystore_uri(keystore_path, key_name, public_keys)
        except KeystoreError:
            pass

    return None


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


def _setup_keystore_key(
    keystore: Optional[Union[Path, str]],
    role_name: str,
    key_name: str,
    scheme: Optional[str],
    length: Optional[int],
    skip_prompt: Optional[bool],
) -> Tuple[Signer, str]:
    generate_new_keys = keystore is None
    signer = None

    def _invalid_key_message(key_name, keystore):
        key_path = Path(keystore, key_name)
        if key_path.is_file():
            print(f"Could not load private key {key_path}")
        else:
            print(f"{key_path} is not a file!")

    if keystore is not None:
        check_keystore_path_usable_in_uri(Path(keystore, key_name))
        keystore_path = str(Path(keystore).expanduser().resolve())
        while signer is None:
            try:
                signer = load_signer_from_private_keystore(
                    keystore_path, key_name, scheme
                )
            except KeystoreError:
                _invalid_key_message(key_name, keystore)

            if signer is None:
                generate_new_keys = skip_prompt is True or click.confirm(
                    "Generate new keys?"
                )
                if not generate_new_keys:
                    if click.confirm("Reuse existing key?"):
                        reused_key_name = input(
                            "Enter name of an existing keystore file: "
                        )
                        Path(keystore, key_name).write_bytes(
                            Path(keystore, reused_key_name).read_bytes()
                        )
                        Path(keystore, key_name + ".pub").write_bytes(
                            Path(keystore, reused_key_name + ".pub").read_bytes()
                        )
                    else:
                        raise KeystoreError(f"Could not load {key_name}")
                else:
                    break
    if generate_new_keys:
        if keystore is None:
            raise KeystoreError(
                f"Cannot generate {key_name}: no keystore to write it to"
            )
        generate_and_write_keypair(Path(keystore, key_name), scheme, length)
        signer = load_signer_from_private_keystore(keystore, key_name, scheme)

    if signer is not None:
        return signer, _get_legacy_keyid(signer.public_key)
    raise KeystoreError(f"Could not load signer {key_name}")


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
