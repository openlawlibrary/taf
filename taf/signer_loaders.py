"""Load the signers of a role from the places that can hold its keys.

Each place, like keystore files, YubiKeys or an HSM, has its own loader.
load_role_signers tries the loaders in order of their priority, so a new place
to keep keys only needs a new loader.
"""

from abc import ABC, abstractmethod
from enum import IntEnum
from functools import partial
from logging import INFO
from pathlib import Path
from typing import Dict, List, Optional

import click
from logdecorator import log_on_start
from securesystemslib.signer import Signer, SSlibKey

from taf import YubikeyMissingLibrary
from taf.api.utils._conf import find_keystore
from taf.exceptions import KeystoreError, SigningError
from taf.keystore import get_keystore_keys_of_role, load_signer_from_keystore_uri
from taf.log import taf_logger
from taf.tuf.repository import MetadataRepository as TUFRepository
from taf.tuf.signer_uris import check_keystore_path, get_yubikey_uri, load_signer
from taf.utils import secret_yes_no_prompt

try:
    import taf.yubikey.yubikey as yk
except ImportError:
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


class KeystoreSignerLoader(SignerLoader):
    """Loads signers from the role's keystore files, e.g. targets1 and targets2"""

    name = "keystore"
    priority = 0
    input_needed = InputNeeded.NONE

    def __init__(self, keystore_path: Optional[Path]):
        self.keystore_path = keystore_path

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


class YubiKeySignerLoader(SignerLoader):
    """Loads signers from YubiKeys. If insert is True, asks the user to insert
    them, otherwise only reads the ones that are already inserted."""

    name = "YubiKey"

    def __init__(
        self,
        taf_repo: TUFRepository,
        insert: bool,
        key_id_pins: Optional[Dict] = None,
    ):
        self.taf_repo = taf_repo
        self.insert = insert
        self.key_id_pins = key_id_pins
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


class HSMSignerLoader(SignerLoader):
    """Loads signers of keys stored on an HSM, using securesystemslib's
    HSMSigner. Needs the taf[hsm] extra. Not implemented yet, so it is not
    one of the loaders load_signers uses."""

    name = "HSM"
    priority = 30
    input_needed = InputNeeded.DEVICE

    def load(
        self, role: str, keys: List[SSlibKey], threshold_reached: bool
    ) -> List[Signer]:
        raise NotImplementedError("Loading signers from an HSM is not supported yet")


@log_on_start(INFO, "Loading signing keys of '{role:s}'", logger=taf_logger)
def load_signers(
    taf_repo: TUFRepository,
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
        KeystoreSignerLoader(keystore_path),
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


def _load_signer_from_keystore(
    keystore_path, key_name, public_keys: List[SSlibKey]
) -> Optional[Signer]:
    if keystore_path is None:
        return None
    if (keystore_path / key_name).is_file():
        check_keystore_path(keystore_path / key_name)
        try:
            return load_signer_from_keystore_uri(keystore_path, key_name, public_keys)
        except KeystoreError:
            pass

    return None


def _load_yubikeys(
    taf_repo: TUFRepository,
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
