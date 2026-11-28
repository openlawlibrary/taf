"""Load the signers of a role from the storages that hold its keys."""

import click
from logging import INFO
from pathlib import Path
from typing import Dict, List, Optional

from logdecorator import log_on_start
from securesystemslib.signer import Signer

from taf.api.utils._conf import find_keystore
from taf.auth_repo import AuthenticationRepository
from taf.exceptions import SigningError
from taf.log import taf_logger
from taf.signers.base import InputNeeded, KeyStorage
from taf.signers.keystore import KeystoreStorage
from taf.signers.yubikey import YubiKeyStorage
from taf.utils import secret_yes_no_prompt


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
    storages: List[KeyStorage] = [
        KeystoreStorage(taf_repo, keystore_path),
        YubiKeyStorage(taf_repo, insert=False, key_id_pins=key_id_pins),
        YubiKeyStorage(taf_repo, insert=True, key_id_pins=key_id_pins),
    ]
    return load_role_signers(
        taf_repo, role, storages, ask_before_input=not use_yubikeys_to_sign
    )


def load_role_signers(
    taf_repo,
    role: str,
    storages: List[KeyStorage],
    ask_before_input: bool = True,
) -> List[Signer]:
    """
    Load signers of a role, trying the storages in order of their priority.
    Storages that need no input load every key they can. The others are used
    until the threshold of signers is reached, and after that only if the user
    wants to load more keys. Before the first storage that needs a device is
    used, the user is asked if they want to sign with it, unless
    ask_before_input is False.
    """
    keys = taf_repo.get_public_keys_of_role(role)
    threshold = taf_repo.get_role_threshold(role)
    signers: Dict[str, Signer] = {}
    used_storages = set()
    used_input = False

    def _missing_keys():
        return [key for key in keys if key.keyid not in signers]

    for storage in sorted(storages, key=lambda storage: storage.priority):
        while _missing_keys():
            threshold_reached = len(signers) >= threshold
            if storage.input_needed != InputNeeded.NONE and threshold_reached:
                if not _load_more_keys(
                    taf_repo, role, used_input or not ask_before_input
                ):
                    return list(signers.values())
            if (
                storage.input_needed == InputNeeded.DEVICE
                and ask_before_input
                and storage.name not in used_storages
                and not click.confirm(f"Sign {role} using {storage.name}(s)?")
            ):
                break

            missing_keyids = {key.keyid for key in _missing_keys()}
            new_signers = [
                signer
                for signer in storage.load_signers(
                    role, _missing_keys(), threshold_reached
                )
                if signer.public_key.keyid in missing_keyids
            ]
            for signer in new_signers:
                signers[signer.public_key.keyid] = signer
            if new_signers:
                used_storages.add(storage.name)
                used_input = used_input or storage.input_needed != InputNeeded.NONE
            if not new_signers or not storage.repeat:
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
