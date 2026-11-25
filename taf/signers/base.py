"""Base class of key storages, and loading a signer from a private key URI."""

from abc import ABC, abstractmethod
from enum import IntEnum
from typing import List, Optional, Tuple

from securesystemslib.exceptions import KeyMismatchError
from securesystemslib.signer import SecretsHandler, Signer, SSlibKey

from taf.models.types import Role


class InputNeeded(IntEnum):
    """What a key storage needs from the user"""

    # e.g. keystore files
    NONE = 0
    # e.g. the PIN of a YubiKey that is already inserted
    SECRET = 1
    # the user has to insert a device
    DEVICE = 2


class KeyStorage(ABC):
    """A place that holds signing keys, like keystore files, YubiKeys or an HSM"""

    # used in prompts, e.g. "Sign targets using YubiKey(s)?"
    name: str = ""
    # storages with a lower priority are tried first
    priority: int = 0
    input_needed: InputNeeded = InputNeeded.NONE
    # if True, load_signers is called again while it finds new signers
    repeat: bool = False

    @abstractmethod
    def load_signers(
        self, role: str, keys: List[SSlibKey], threshold_reached: bool
    ) -> List[Signer]:
        """Return signers for any of keys, which are the role's keys that are
        not loaded yet"""

    @abstractmethod
    def setup_keys(self, role: Role) -> Tuple[List[Signer], List[SSlibKey]]:
        """Load or create the keys of a role that is not in metadata yet.
        Return signers of the keys that were loaded, and public keys of the
        role's other keys"""


def load_signer(
    uri: str,
    public_keys: List[SSlibKey],
    secrets_handler: Optional[SecretsHandler] = None,
) -> Optional[Signer]:
    """Return a signer for the first of ``public_keys`` that matches the
    private key, or None. YubiKey keys are not checked, so pass only the key
    read from the device."""
    for public_key in public_keys:
        try:
            return Signer.from_priv_key_uri(uri, public_key, secrets_handler)
        except (KeyMismatchError, ValueError):
            continue
    return None
