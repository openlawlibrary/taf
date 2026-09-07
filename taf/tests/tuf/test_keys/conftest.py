import pytest
import shutil

import taf.yubikey.yubikey as yk
from taf.tests.conftest import create_authentication_repository
from taf.tools.yubikey.yubikey_utils import FakeYubiKey, _yk_piv_ctrl_mock
from taf.utils import on_rm_error
from taf.models.converter import from_dict
from taf.models.types import RolesKeysData
from taf.tuf.repository import MetadataRepository
from taf.yubikey.yubikey_manager import PinManager


@pytest.fixture
def fake_single_yubikey(monkeypatch):
    """Pretend exactly one YubiKey (serial ``1234``) is inserted."""
    monkeypatch.setattr(yk, "get_serial_nums", lambda: ["1234"])


@pytest.fixture
def fake_yubikey(monkeypatch, keystore):
    """A fake inserted YubiKey backed by a real keystore key in SIGNATURE,
    with put_key/put_certificate/reset emulated per-slot so slot-management
    behavior (setup, get_slot_status, get_piv_public_keys_tuf) can be tested
    without real hardware."""
    monkeypatch.setattr(yk, "_yk_piv_ctrl", _yk_piv_ctrl_mock)
    key = FakeYubiKey(keystore / "root1", keystore / "root1.pub", scheme=None)
    key.insert()
    yield key
    key.remove()


@pytest.fixture
def make_fake_yubikey(monkeypatch, keystore):
    """Factory for fake inserted YubiKeys, each backed by a given keystore
    key (occupying SIGNATURE) and optionally pre-provisioned with more keys
    in other slots. Each call creates one independent device; all are
    removed automatically at teardown.

    Usage:
        device = make_fake_yubikey("targets")
        device = make_fake_yubikey(
            "snapshot", extra_slots={SLOT.AUTHENTICATION: "timestamp"}
        )
    """
    monkeypatch.setattr(yk, "_yk_piv_ctrl", _yk_piv_ctrl_mock)
    created = []

    def _make(key_name, extra_slots=None):
        device = FakeYubiKey(
            keystore / key_name, keystore / f"{key_name}.pub", scheme=None
        )
        device.insert()
        for slot, other_key_name in (extra_slots or {}).items():
            yk.setup(
                pin=device.pin,
                serial=device.serial,
                cert_cn=f"{other_key_name} key",
                private_key_pem=(keystore / other_key_name).read_bytes(),
                slot=slot,
            )
        created.append(device)
        return device

    yield _make

    for device in created:
        device.remove()


@pytest.fixture
def create_auth_repo(repo_path, keystore, keystore_no_yubikeys_path):
    """Factory wrapping create_authentication_repository: root is signed
    with root1+root2, both already present in the shared keystore fixture,
    so it can be pointed at directly - nothing needs generating or writing.
    Built under the test's own repo_path, cleaned up with it.
    """

    def _create(pin_manager=None):
        return create_authentication_repository(
            repo_path,
            pin_manager if pin_manager is not None else PinManager(),
            "test/auth",
            keystore_no_yubikeys_path,
            is_test_repo=True,
            keystore=keystore,
        )

    return _create


@pytest.fixture(autouse=False)
def tuf_repo(
    tuf_repo_path, signers_with_delegations, with_delegations_no_yubikeys_input
):
    repo = MetadataRepository(tuf_repo_path)
    roles_keys_data = from_dict(with_delegations_no_yubikeys_input, RolesKeysData)
    repo.create(roles_keys_data, signers_with_delegations)
    yield repo
    shutil.rmtree(tuf_repo_path, onerror=on_rm_error)
