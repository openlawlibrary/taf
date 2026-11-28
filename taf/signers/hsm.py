"""HSMs. Loading their signers is not implemented yet."""

from typing import List, Tuple

from securesystemslib.signer import Signer, SSlibKey

from taf.models.types import Role
from taf.signers.base import InputNeeded, KeyStorage


class HSMStorage(KeyStorage):
    """Keys stored on an HSM. Needs the taf[hsm] extra. Not implemented yet,
    so load_signers does not use it."""

    name = "HSM"
    priority = 30
    input_needed = InputNeeded.DEVICE

    def load_signers(
        self, role: str, keys: List[SSlibKey], threshold_reached: bool
    ) -> List[Signer]:
        raise NotImplementedError("Loading signers from an HSM is not supported yet")

    def setup_keys(self, role: Role) -> Tuple[List[Signer], List[SSlibKey]]:
        raise NotImplementedError("Setting up keys on an HSM is not supported yet")
