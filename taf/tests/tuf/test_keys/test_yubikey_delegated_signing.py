"""Regression coverage for a reported multi-YubiKey bug: with two YubiKeys
inserted, where only one of them holds a key with authority over a
delegated role, signing was reported to fail depending on which key got
checked first."""

import pytest
from tuf.api.metadata import Metadata
from yubikit.piv import SLOT

from taf.api.targets import register_target_files
from taf.auth_repo import AuthenticationRepository
from taf.tuf.keys import load_signer_from_file
from taf.yubikey.yubikey_manager import PinManager
import taf.yubikey.yubikey as yk


def _pin_manager(*devices) -> PinManager:
    pin_manager = PinManager()
    for device in devices:
        pin_manager.add_pin(device.serial, device.pin)
    return pin_manager


def _block_reprompt(monkeypatch):
    def _unexpected_reprompt(*_args, **_kwargs):
        raise AssertionError(
            "unexpected re-prompt: yubikey_prompt retried instead of finding "
            "the authorized YubiKey among the inserted devices"
        )

    monkeypatch.setattr(yk, "getpass", _unexpected_reprompt)


def _make_delegated_role_device(make_fake_yubikey, keystore_delegations):
    return make_fake_yubikey(
        "delegated_role1",
        extra_slots={SLOT.AUTHENTICATION: "delegated_role2"},
        keystore_path=keystore_delegations,
    )


def _make_unauthorized_device(make_fake_yubikey, keystore_delegations):
    return make_fake_yubikey("targets1", keystore_path=keystore_delegations)


def _insert_in_order(*devices):
    for device in devices:
        device.remove()
    for device in devices:
        device.insert()


def _write_target(path, text="hello"):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def _write_signing_keystore(tmp_path, source_keystore, names=("snapshot", "timestamp")):
    signing_keystore = tmp_path / "signing_keystore"
    signing_keystore.mkdir()
    for name in names:
        (signing_keystore / name).write_bytes((source_keystore / name).read_bytes())
        (signing_keystore / f"{name}.pub").write_bytes(
            (source_keystore / f"{name}.pub").read_bytes()
        )
    return signing_keystore


@pytest.mark.parametrize("authorized_inserted_first", [True, False])
def test_read_and_check_yubikeys_skips_unauthorized_device_for_delegated_role(
    make_fake_yubikey,
    keystore_delegations,
    create_delegated_auth_repo,
    authorized_inserted_first,
):
    authorized = _make_delegated_role_device(make_fake_yubikey, keystore_delegations)
    unauthorized = _make_unauthorized_device(make_fake_yubikey, keystore_delegations)
    if not authorized_inserted_first:
        _insert_in_order(unauthorized, authorized)

    taf_repo = create_delegated_auth_repo()

    result = yk._read_and_check_yubikeys(
        role="delegated_role",
        taf_repo=taf_repo,
        pin_manager=_pin_manager(authorized, unauthorized),
        pin_confirm=False,
        pin_repeat=False,
        prompt_message=None,
        key_names=["delegated_role1", "delegated_role2"],
        retrying=False,
        hide_already_loaded_message=True,
        hide_threshold_message=True,
        key_id_pins=None,
    )

    assert result is not None
    role1_key = load_signer_from_file(
        keystore_delegations / "delegated_role1"
    ).public_key
    role2_key = load_signer_from_file(
        keystore_delegations / "delegated_role2"
    ).public_key
    found_keyids = {entry[0].keyid for entry in result}
    assert found_keyids == {role1_key.keyid, role2_key.keyid}
    assert all(entry[1] == authorized.serial for entry in result)


@pytest.mark.parametrize("authorized_inserted_first", [True, False])
def test_sign_delegated_role_with_unauthorized_yubikey_inserted(
    make_fake_yubikey,
    keystore_delegations,
    create_delegated_auth_repo,
    tmp_path,
    monkeypatch,
    authorized_inserted_first,
):
    _block_reprompt(monkeypatch)

    authorized = _make_delegated_role_device(make_fake_yubikey, keystore_delegations)
    unauthorized = _make_unauthorized_device(make_fake_yubikey, keystore_delegations)
    if not authorized_inserted_first:
        _insert_in_order(unauthorized, authorized)

    pin_manager = _pin_manager(authorized, unauthorized)
    taf_repo = create_delegated_auth_repo(pin_manager)

    metadata_path = taf_repo.path / "metadata"
    delegated_md_before = Metadata.from_file(str(metadata_path / "delegated_role.json"))
    version_before = delegated_md_before.signed.version

    _write_target(taf_repo.targets_path / "dir1" / "a-new-target.txt")
    signing_keystore = _write_signing_keystore(tmp_path, keystore_delegations)

    auth_repo = AuthenticationRepository(
        path=str(taf_repo.path), pin_manager=pin_manager
    )

    register_target_files(
        str(taf_repo.path),
        pin_manager,
        keystore=str(signing_keystore),
        update_snapshot_and_timestamp=True,
        push=False,
    )

    assert "dir1/a-new-target.txt" in auth_repo.get_signed_target_files()

    targets_md = Metadata.from_file(str(metadata_path / "targets.json"))
    delegated_md_after = Metadata.from_file(str(metadata_path / "delegated_role.json"))
    targets_md.verify_delegate("delegated_role", delegated_md_after)
    assert delegated_md_after.signed.version > version_before


@pytest.mark.parametrize("device_a_inserted_first", [True, False])
def test_sign_two_delegated_roles_each_with_its_own_yubikey_in_one_command(
    make_fake_yubikey,
    keystore_delegations,
    create_delegated_auth_repo,
    tmp_path,
    monkeypatch,
    device_a_inserted_first,
):
    _block_reprompt(monkeypatch)

    device_delegated = _make_delegated_role_device(
        make_fake_yubikey, keystore_delegations
    )
    device_inner = make_fake_yubikey("inner_role", keystore_path=keystore_delegations)
    if not device_a_inserted_first:
        _insert_in_order(device_inner, device_delegated)

    pin_manager = _pin_manager(device_delegated, device_inner)
    taf_repo = create_delegated_auth_repo(pin_manager)

    metadata_path = taf_repo.path / "metadata"
    versions_before = {
        role: Metadata.from_file(str(metadata_path / f"{role}.json")).signed.version
        for role in ("delegated_role", "inner_role")
    }

    _write_target(taf_repo.targets_path / "dir1" / "a-new-target.txt")
    _write_target(taf_repo.targets_path / "dir2" / "path2")
    signing_keystore = _write_signing_keystore(tmp_path, keystore_delegations)

    auth_repo = AuthenticationRepository(
        path=str(taf_repo.path), pin_manager=pin_manager
    )

    register_target_files(
        str(taf_repo.path),
        pin_manager,
        keystore=str(signing_keystore),
        update_snapshot_and_timestamp=True,
        push=False,
    )

    signed_targets = auth_repo.get_signed_target_files()
    assert "dir1/a-new-target.txt" in signed_targets
    assert "dir2/path2" in signed_targets

    targets_md = Metadata.from_file(str(metadata_path / "targets.json"))
    delegated_md = Metadata.from_file(str(metadata_path / "delegated_role.json"))
    inner_md = Metadata.from_file(str(metadata_path / "inner_role.json"))
    targets_md.verify_delegate("delegated_role", delegated_md)
    delegated_md.verify_delegate("inner_role", inner_md)
    assert delegated_md.signed.version > versions_before["delegated_role"]
    assert inner_md.signed.version > versions_before["inner_role"]
