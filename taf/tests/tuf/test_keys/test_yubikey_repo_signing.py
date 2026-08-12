"""Integration test: a real authentication repository, created and updated
through the real CLI-level API (taf.api.repository.create_repository,
taf.api.targets.register_target_files), signed with fake YubiKeys standing
in for real hardware - one device for targets, a second device holding two
different keys (one per PIV slot) for snapshot and timestamp.

Unlike taf/tests/tuf/test_keys/test_yubikey_slots.py (which exercises the
low-level discovery/signing functions directly), this drives the same
interactive setup flow a real user would go through, mocking only the
genuine I/O boundaries (PIN/confirm/prompt input) - never taf's own
collaborator logic.
"""

import json
from pathlib import Path
from unittest import mock

import pytest
from tuf.api.metadata import Metadata
from yubikit.piv import SLOT

import taf.keys as taf_keys
import taf.yubikey.yubikey as yk
from taf.api.repository import create_repository
from taf.api.targets import register_target_files
from taf.auth_repo import AuthenticationRepository
from taf.tools.yubikey.yubikey_utils import FakeYubiKey, _yk_piv_ctrl_mock
from taf.yubikey.yubikey_manager import PinManager


@pytest.fixture
def two_fake_yubikeys(monkeypatch, keystore):
    """Two fake devices: device_b (targets' key, SIGNATURE only) and
    device_a, pre-provisioned with two *different* keys in two different
    slots - snapshot's in SIGNATURE, timestamp's in AUTHENTICATION - the
    same way a real device would be set up ahead of time with
    `taf yubikey setup-test-key` before being reused during repo creation.
    """
    monkeypatch.setattr(yk, "_yk_piv_ctrl", _yk_piv_ctrl_mock)

    device_b = FakeYubiKey(keystore / "targets", keystore / "targets.pub", scheme=None)
    device_a = FakeYubiKey(
        keystore / "snapshot", keystore / "snapshot.pub", scheme=None
    )
    device_b.insert()
    device_a.insert()
    yk.setup(
        pin=device_a.pin,
        serial=device_a.serial,
        cert_cn="Timestamp key",
        private_key_pem=(keystore / "timestamp").read_bytes(),
        slot=SLOT.AUTHENTICATION,
    )
    # only device_b should be inserted when repo creation starts - the
    # confirm-mock below inserts device_a once targets' setup is done
    device_a.remove()

    yield device_a, device_b

    device_a.remove()
    device_b.remove()


def _make_confirm_side_effect(device_a, device_b):
    """Sequences taf's interactive "reuse already set up Yubikey?" prompt -
    every role reuses an already-set-up key (device_b's default SIGNATURE
    key for targets, then device_a's two slots for snapshot/timestamp), so
    the answer is always "yes"; this only needs to swap which device is
    "inserted" between targets and snapshot. Every other confirm() in the
    flow (generate/write keystore keys, etc.) is also answered "yes" to
    just proceed.
    """
    reuse_calls = {"count": 0}

    def _side_effect(message, *args, **kwargs):
        if message == "Do you want to reuse already set up Yubikey?":
            reuse_calls["count"] += 1
            if reuse_calls["count"] == 2:
                device_b.remove()
                device_a.insert()
        return True

    return _side_effect


def test_create_repo_and_sign_target_update_across_devices_and_slots(
    two_fake_yubikeys, keystore, tmp_path
):
    device_a, device_b = two_fake_yubikeys
    pin_manager = PinManager()
    pin_manager.add_pin(device_a.serial, device_a.pin)
    pin_manager.add_pin(device_b.serial, device_b.pin)

    repo_path = tmp_path / "auth"
    scratch_keystore = tmp_path / "keystore"
    scratch_keystore.mkdir()

    roles_key_infos_path = tmp_path / "keys-description.json"
    roles_key_infos_path.write_text(
        json.dumps(
            {
                "roles": {
                    "root": {"number": 1, "threshold": 1},
                    "targets": {"number": 1, "threshold": 1, "yubikey": True},
                    "snapshot": {"number": 1, "threshold": 1, "yubikey": True},
                    "timestamp": {"yubikey": True},
                }
            }
        )
    )

    def _input_side_effect(prompt="", *args, **kwargs):
        # keeping this blank avoids encrypting the generated keystore key
        # with a password load_signer_from_pem is never given back
        if "password" in prompt.lower():
            return ""
        return "Test key holder"

    # role setup needs devices inserted one at a time (taf refuses to guess
    # which of several not-yet-loaded devices a role means), but the actual
    # metadata signing that follows happens as one batch across all roles,
    # needing every device that was used present at once - so device_b is
    # brought back once timestamp (the last role) finishes its own setup,
    # before any signing happens.
    real_setup_yubikey = taf_keys._setup_yubikey

    def _setup_yubikey_wrapper(auth_repo, role_name, key_name, *args, **kwargs):
        result = real_setup_yubikey(auth_repo, role_name, key_name, *args, **kwargs)
        if role_name == "timestamp":
            device_b.insert()
        return result

    with mock.patch(
        "click.confirm", side_effect=_make_confirm_side_effect(device_a, device_b)
    ), mock.patch("click.prompt", side_effect=[2, 1]), mock.patch(
        "builtins.input", side_effect=_input_side_effect
    ), mock.patch(
        "taf.keys._setup_yubikey", side_effect=_setup_yubikey_wrapper
    ):
        create_repository(
            str(repo_path),
            pin_manager,
            keystore=str(scratch_keystore),
            roles_key_infos=str(roles_key_infos_path),
            commit=True,
            test=True,
        )

    metadata_path = repo_path / "metadata"
    root_md = Metadata.from_file(str(metadata_path / "root.json"))
    versions_before = {}
    for role in ("targets", "snapshot", "timestamp"):
        role_md = Metadata.from_file(str(metadata_path / f"{role}.json"))
        root_md.verify_delegate(role, role_md)
        versions_before[role] = role_md.signed.version

    # add a target file and sign the update - both devices stay inserted;
    # this goes through _read_and_check_yubikeys (role-validity-based
    # discovery), not the interactive setup flow, so no confirm/prompt
    # mocking is needed here
    auth_repo = AuthenticationRepository(path=str(repo_path), pin_manager=pin_manager)
    target_file = auth_repo.targets_path / "a-new-target.txt"
    target_file.write_text("hello")

    register_target_files(
        str(repo_path),
        pin_manager,
        keystore=str(scratch_keystore),
        update_snapshot_and_timestamp=True,
        push=False,
    )

    assert "a-new-target.txt" in auth_repo.get_signed_target_files()

    root_md = Metadata.from_file(str(metadata_path / "root.json"))
    updated_targets_md = Metadata.from_file(str(metadata_path / "targets.json"))
    updated_snapshot_md = Metadata.from_file(str(metadata_path / "snapshot.json"))
    updated_timestamp_md = Metadata.from_file(str(metadata_path / "timestamp.json"))
    root_md.verify_delegate("targets", updated_targets_md)
    root_md.verify_delegate("snapshot", updated_snapshot_md)
    root_md.verify_delegate("timestamp", updated_timestamp_md)

    # re-signing must have actually happened, not a no-op
    assert updated_targets_md.signed.version > versions_before["targets"]
    assert updated_snapshot_md.signed.version > versions_before["snapshot"]
    assert updated_timestamp_md.signed.version > versions_before["timestamp"]
