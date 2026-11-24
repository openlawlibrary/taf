import click
import pytest
import shutil

from cryptography.hazmat.primitives import serialization
from yubikit.piv import SLOT

from taf.constants import DEFAULT_RSA_SIGNATURE_SCHEME

import taf.signer_loaders
import taf.yubikey.yubikey as yk
from taf.api.targets import register_target_files
from taf.signer_loaders import SignerLoader
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
    key = FakeYubiKey(
        keystore / "root1", keystore / "root1.pub", scheme=DEFAULT_RSA_SIGNATURE_SCHEME
    )
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

    def _make(
        key_name,
        extra_slots=None,
        keystore_path=None,
        scheme=DEFAULT_RSA_SIGNATURE_SCHEME,
    ):
        source_keystore = keystore_path if keystore_path is not None else keystore
        device = FakeYubiKey(
            source_keystore / key_name,
            source_keystore / f"{key_name}.pub",
            scheme=scheme,
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
    hang instead of a clean assertion failure. Asking the user to confirm
    something, or whether to load more keys, fails the same way."""

    def _unexpected_reprompt(*_args, **_kwargs):
        raise AssertionError(
            "unexpected re-prompt: yubikey_prompt retried instead of finding "
            "the authorized YubiKey among the inserted devices"
        )

    def _unexpected_prompt(message, *_args, **_kwargs):
        raise AssertionError(f"unexpected prompt: {message}")

    monkeypatch.setattr(yk, "getpass", _unexpected_reprompt)
    monkeypatch.setattr(click, "confirm", _unexpected_prompt)
    monkeypatch.setattr(taf.signer_loaders, "secret_yes_no_prompt", _unexpected_prompt)


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


def same_public_key(key, other) -> bool:
    """Check if two public keys are the same key. Each one can be a
    cryptography public key or PEM data."""

    def _der(public_key):
        if isinstance(public_key, str):
            public_key = public_key.encode()
        if isinstance(public_key, bytes):
            public_key = serialization.load_pem_public_key(public_key)
        return public_key.public_bytes(
            serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo
        )

    return _der(key) == _der(other)


def pin_manager_for(*devices):
    pin_manager = PinManager()
    for device in devices:
        pin_manager.add_pin(device.serial, device.pin)
    return pin_manager


def verify_and_get_versions(auth_repo, *roles):
    """Verify each role's metadata against root and return its version."""
    root_md = auth_repo.open("root")
    versions = {}
    for role in roles:
        role_md = auth_repo.open(role)
        root_md.verify_delegate(role, role_md)
        versions[role] = role_md.signed.version
    return versions


def sign_target_update(auth_repo, signing_keystore, target_path="a-new-target.txt"):
    """Write a target file at target_path (relative to the targets directory),
    register it and update snapshot and timestamp, signing with whatever
    signing_keystore and the inserted YubiKeys provide."""
    write_target(auth_repo.targets_path / target_path)
    register_target_files(
        str(auth_repo.path),
        auth_repo.pin_manager,
        keystore=str(signing_keystore),
        update_snapshot_and_timestamp=True,
        push=False,
    )
    assert target_path in auth_repo.get_signed_target_files()


@pytest.fixture
def decline_prompts(monkeypatch):
    """Answer no to every confirmation and to the "load more keys?" question"""

    def _decline(*_args, **_kwargs):
        return False

    monkeypatch.setattr(click, "confirm", _decline)
    monkeypatch.setattr(taf.signer_loaders, "secret_yes_no_prompt", _decline)


class FakeSignerLoader(SignerLoader):
    """A signer loader that always returns the given signers, and appends its
    name to calls each time it is used, so tests can check the loading order"""

    def __init__(self, name, priority, input_needed, signers, calls):
        self.name = name
        self.priority = priority
        self.input_needed = input_needed
        self._signers = signers
        self._calls = calls

    def load(self, role, keys, threshold_reached):
        self._calls.append(self.name)
        return self._signers

    def setup_keys(self, role):
        raise NotImplementedError
