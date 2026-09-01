"""Regression coverage for a reported multi-YubiKey bug: with two YubiKeys
inserted, where only one of them holds a key with authority over a
delegated role, signing was reported to fail depending on which key got
checked first."""

import pytest
from tuf.api.metadata import Metadata

from taf.api.targets import register_target_files
from taf.auth_repo import AuthenticationRepository
from taf.tests.tuf.test_keys.conftest import (
    insert_in_order,
    write_signing_keystore,
    write_target,
)
from taf.tuf.keys import load_signer_from_file
from taf.yubikey.yubikey_manager import PinManager
import taf.yubikey.yubikey as yk


def _pin_manager(*devices) -> PinManager:
    pin_manager = PinManager()
    for device in devices:
        pin_manager.add_pin(device.serial, device.pin)
    return pin_manager


@pytest.mark.parametrize("authorized_inserted_first", [True, False])
def test_read_and_check_yubikeys_skips_unauthorized_device_for_delegated_role(
    delegated_role_device,
    unauthorized_device,
    keystore_delegations,
    create_delegated_auth_repo,
    authorized_inserted_first,
):
    if not authorized_inserted_first:
        insert_in_order(unauthorized_device, delegated_role_device)

    taf_repo = create_delegated_auth_repo()

    result = yk._read_and_check_yubikeys(
        role="delegated_role",
        taf_repo=taf_repo,
        pin_manager=_pin_manager(delegated_role_device, unauthorized_device),
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
    assert all(entry[1] == delegated_role_device.serial for entry in result)


@pytest.mark.parametrize("authorized_inserted_first", [True, False])
def test_sign_delegated_role_with_unauthorized_yubikey_inserted(
    delegated_role_device,
    unauthorized_device,
    keystore_delegations,
    create_delegated_auth_repo,
    tmp_path,
    block_reprompt,
    authorized_inserted_first,
):
    if not authorized_inserted_first:
        insert_in_order(unauthorized_device, delegated_role_device)

    pin_manager = _pin_manager(delegated_role_device, unauthorized_device)
    taf_repo = create_delegated_auth_repo(pin_manager)

    metadata_path = taf_repo.path / "metadata"
    delegated_md_before = Metadata.from_file(str(metadata_path / "delegated_role.json"))
    version_before = delegated_md_before.signed.version

    write_target(taf_repo.targets_path / "dir1" / "a-new-target.txt")
    signing_keystore = write_signing_keystore(tmp_path, keystore_delegations)

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
    delegated_role_device,
    make_fake_yubikey,
    keystore_delegations,
    create_delegated_auth_repo,
    tmp_path,
    block_reprompt,
    device_a_inserted_first,
):
    device_inner = make_fake_yubikey("inner_role", keystore_path=keystore_delegations)
    if not device_a_inserted_first:
        insert_in_order(device_inner, delegated_role_device)

    pin_manager = _pin_manager(delegated_role_device, device_inner)
    taf_repo = create_delegated_auth_repo(pin_manager)

    metadata_path = taf_repo.path / "metadata"
    versions_before = {
        role: Metadata.from_file(str(metadata_path / f"{role}.json")).signed.version
        for role in ("delegated_role", "inner_role")
    }

    write_target(taf_repo.targets_path / "dir1" / "a-new-target.txt")
    write_target(taf_repo.targets_path / "dir2" / "path2")
    signing_keystore = write_signing_keystore(tmp_path, keystore_delegations)

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
