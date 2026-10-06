"""Regression coverage for a reported multi-YubiKey bug: with two YubiKeys
inserted, where only one of them holds a key with authority over a
delegated role, signing was reported to fail depending on which key got
checked first."""

import pytest

from taf.tests.tuf.test_keys.conftest import (
    insert_in_order,
    pin_manager_for,
    sign_target_update,
    write_signing_keystore,
    write_target,
)
from taf.tuf.keys import load_signer_from_file
import taf.yubikey.yubikey as yk


@pytest.mark.parametrize("device_a_inserted_first", [True, False])
def test_read_and_check_yubikeys_assigns_distinct_names_to_two_devices_of_same_role(
    make_fake_yubikey,
    keystore_delegations,
    create_delegated_auth_repo,
    real_public_key,
    device_a_inserted_first,
):
    """https://github.com/openlawlibrary/taf/issues/611 - with two valid
    YubiKeys for the same role inserted together, both got prompted for
    under the same default key name."""
    device1 = make_fake_yubikey("targets1", keystore_path=keystore_delegations)
    device2 = make_fake_yubikey("targets2", keystore_path=keystore_delegations)
    if not device_a_inserted_first:
        insert_in_order(device2, device1)

    taf_repo = create_delegated_auth_repo()
    taf_repo.add_default_names_of_role("targets")

    result = yk._read_and_check_yubikeys(
        role="targets",
        taf_repo=taf_repo,
        pin_manager=pin_manager_for(device1, device2),
        pin_confirm=False,
        pin_repeat=False,
        prompt_message=None,
        key_names=taf_repo.get_key_names_of_role("targets"),
        retrying=False,
        hide_already_loaded_message=True,
        hide_threshold_message=True,
        key_id_pins=None,
    )

    assert result is not None
    names_by_keyid = {entry[0].keyid: entry[2] for entry in result}
    assert names_by_keyid[real_public_key("targets1").keyid] == "targets1"
    assert names_by_keyid[real_public_key("targets2").keyid] == "targets2"


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
        pin_manager=pin_manager_for(delegated_role_device, unauthorized_device),
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

    pin_manager = pin_manager_for(delegated_role_device, unauthorized_device)
    taf_repo = create_delegated_auth_repo(pin_manager)

    version_before = taf_repo.open("delegated_role").signed.version

    sign_target_update(
        taf_repo,
        write_signing_keystore(tmp_path, keystore_delegations),
        "dir1/a-new-target.txt",
    )

    targets_md = taf_repo.open("targets")
    delegated_md_after = taf_repo.open("delegated_role")
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

    pin_manager = pin_manager_for(delegated_role_device, device_inner)
    taf_repo = create_delegated_auth_repo(pin_manager)

    versions_before = {
        role: taf_repo.open(role).signed.version
        for role in ("delegated_role", "inner_role")
    }

    write_target(taf_repo.targets_path / "dir2" / "path2")
    sign_target_update(
        taf_repo,
        write_signing_keystore(tmp_path, keystore_delegations),
        "dir1/a-new-target.txt",
    )
    assert "dir2/path2" in taf_repo.get_signed_target_files()

    targets_md = taf_repo.open("targets")
    delegated_md = taf_repo.open("delegated_role")
    inner_md = taf_repo.open("inner_role")
    targets_md.verify_delegate("delegated_role", delegated_md)
    delegated_md.verify_delegate("inner_role", inner_md)
    assert delegated_md.signed.version > versions_before["delegated_role"]
    assert inner_md.signed.version > versions_before["inner_role"]
