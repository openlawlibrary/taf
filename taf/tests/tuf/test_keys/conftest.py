import pytest
import shutil

from taf.utils import on_rm_error
from taf.models.converter import from_dict
from taf.models.types import RolesKeysData
from taf.tuf.repository import MetadataRepository


@pytest.fixture
def fake_single_yubikey(monkeypatch):
    """Pretend exactly one YubiKey (serial ``1234``) is inserted."""
    # Imported lazily: taf.yubikey.yubikey pulls in the optional `ykman`
    # dependency, which need not be installed to collect the rest of this
    # directory's tests.
    import taf.yubikey.yubikey as yk

    monkeypatch.setattr(yk, "get_serial_nums", lambda: ["1234"])


@pytest.fixture(autouse=False)
def tuf_repo(
    tuf_repo_path, signers_with_delegations, with_delegations_no_yubikeys_input
):
    repo = MetadataRepository(tuf_repo_path)
    roles_keys_data = from_dict(with_delegations_no_yubikeys_input, RolesKeysData)
    repo.create(roles_keys_data, signers_with_delegations)
    yield repo
    shutil.rmtree(tuf_repo_path, onerror=on_rm_error)
