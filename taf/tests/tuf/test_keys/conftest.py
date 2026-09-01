import pytest
import shutil

from yubikit.piv import SLOT

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
        # flash from a different keystore directory (e.g. one that has
        # delegated roles' keys):
        device = make_fake_yubikey("delegated_role1", keystore_path=keystore_delegations)
    """
    monkeypatch.setattr(yk, "_yk_piv_ctrl", _yk_piv_ctrl_mock)
    created = []

    def _make(key_name, extra_slots=None, keystore_path=None):
        source_keystore = keystore_path if keystore_path is not None else keystore
        device = FakeYubiKey(
            source_keystore / key_name,
            source_keystore / f"{key_name}.pub",
            scheme=None,
        )
        device.insert()
        for slot, other_key_name in (extra_slots or {}).items():
            yk.setup(
                pin=device.pin,
                serial=device.serial,
                cert_cn=f"{other_key_name} key",
                private_key_pem=(source_keystore / other_key_name).read_bytes(),
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


@pytest.fixture
def create_delegated_auth_repo(
    repo_path, keystore_delegations, with_delegations_no_yubikeys_path
):
    """Factory wrapping create_authentication_repository: builds a repo with
    delegations (targets -> delegated_role -> inner_role), signed entirely
    with keys already present in the keystore_delegations fixture, so
    nothing needs generating or writing. Built under the test's own
    repo_path, cleaned up with it.
    """

    def _create(pin_manager=None):
        return create_authentication_repository(
            repo_path,
            pin_manager if pin_manager is not None else PinManager(),
            "test/auth",
            with_delegations_no_yubikeys_path,
            is_test_repo=True,
            keystore=keystore_delegations,
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


@pytest.fixture
def delegated_role_device(make_fake_yubikey, keystore_delegations):
    """A fake YubiKey holding both of delegated_role's keys (SIGNATURE +
    AUTHENTICATION), from keystore_delegations."""
    return make_fake_yubikey(
        "delegated_role1",
        extra_slots={SLOT.AUTHENTICATION: "delegated_role2"},
        keystore_path=keystore_delegations,
    )


@pytest.fixture
def unauthorized_device(make_fake_yubikey, keystore_delegations):
    """A fake YubiKey valid for 'targets', not for 'delegated_role'."""
    return make_fake_yubikey("targets1", keystore_path=keystore_delegations)


@pytest.fixture
def block_reprompt(monkeypatch):
    """Fail loudly instead of hanging if yubikey_prompt retries - guards
    against yubikey_prompt's unbounded retry loop turning a real bug into a
    hang instead of a clean assertion failure."""

    def _unexpected_reprompt(*_args, **_kwargs):
        raise AssertionError(
            "unexpected re-prompt: yubikey_prompt retried instead of finding "
            "the authorized YubiKey among the inserted devices"
        )

    monkeypatch.setattr(yk, "getpass", _unexpected_reprompt)


def insert_in_order(*devices):
    """Remove and re-insert devices in the given order, so get_serial_nums()
    (which reflects INSERTED_YUBIKEYS' insertion order) enumerates them in
    that order."""
    for device in devices:
        device.remove()
    for device in devices:
        device.insert()


def write_target(path, text="hello"):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def write_signing_keystore(tmp_path, source_keystore, names=("snapshot", "timestamp")):
    signing_keystore = tmp_path / "signing_keystore"
    signing_keystore.mkdir()
    for name in names:
        (signing_keystore / name).write_bytes((source_keystore / name).read_bytes())
        (signing_keystore / f"{name}.pub").write_bytes(
            (source_keystore / f"{name}.pub").read_bytes()
        )
    return signing_keystore
