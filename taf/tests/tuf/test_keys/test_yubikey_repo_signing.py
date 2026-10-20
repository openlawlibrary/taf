import pytest
from yubikit.piv import SLOT

import taf.utils
from taf.api.api_workflow import key_management_context
from taf.api.metadata import update_snapshot_and_timestamp
from taf.tests.tuf.test_keys.conftest import (
    pin_manager_for,
    sign_target_update,
    verify_and_get_versions,
    write_signing_keystore,
)
from taf.tools.yubikey.yubikey_utils import VALID_PIN
from taf.tuf.keys import load_signer_from_file

ROLES = ("targets", "snapshot", "timestamp")


def test_create_repo_and_sign_target_update_across_devices_and_slots(
    make_fake_yubikey, keystore, create_auth_repo, tmp_path
):
    device_b = make_fake_yubikey("targets")
    device_a = make_fake_yubikey(
        "snapshot", extra_slots={SLOT.AUTHENTICATION: "timestamp"}
    )
    auth_repo = create_auth_repo(pin_manager_for(device_a, device_b))
    versions_before = verify_and_get_versions(auth_repo, *ROLES)

    sign_target_update(auth_repo, write_signing_keystore(tmp_path, keystore, names=()))

    versions_after = verify_and_get_versions(auth_repo, *ROLES)
    for role in ROLES:
        assert versions_after[role] > versions_before[role]


def test_sign_target_update_with_every_role_in_its_own_slot_of_one_device(
    make_fake_yubikey, keystore, create_auth_repo, tmp_path
):
    device = make_fake_yubikey(
        "targets",
        extra_slots={
            SLOT.AUTHENTICATION: "snapshot",
            SLOT.KEY_MANAGEMENT: "timestamp",
        },
    )
    auth_repo = create_auth_repo(pin_manager_for(device))
    versions_before = verify_and_get_versions(auth_repo, *ROLES)

    sign_target_update(auth_repo, write_signing_keystore(tmp_path, keystore, names=()))

    versions_after = verify_and_get_versions(auth_repo, *ROLES)
    for role in ROLES:
        assert versions_after[role] > versions_before[role]


@pytest.mark.parametrize("split_across_devices", [False, True])
def test_update_snapshot_and_timestamp_signs_with_keys_in_non_signature_slots(
    make_fake_yubikey, keystore, create_auth_repo, tmp_path, split_across_devices
):
    if split_across_devices:
        devices = [
            make_fake_yubikey("root2", extra_slots={SLOT.AUTHENTICATION: "snapshot"}),
            make_fake_yubikey("root3", extra_slots={SLOT.KEY_MANAGEMENT: "timestamp"}),
        ]
    else:
        devices = [
            make_fake_yubikey(
                "root2",
                extra_slots={
                    SLOT.AUTHENTICATION: "snapshot",
                    SLOT.KEY_MANAGEMENT: "timestamp",
                },
            )
        ]
    pin_manager = pin_manager_for(*devices)
    auth_repo = create_auth_repo(pin_manager)
    versions_before = verify_and_get_versions(auth_repo, *ROLES)

    update_snapshot_and_timestamp(
        str(auth_repo.path),
        pin_manager,
        keystore=str(write_signing_keystore(tmp_path, keystore, names=())),
        roles_to_sync=["targets"],
        commit_msg="Update snapshot and timestamp",
        push=False,
    )

    versions_after = verify_and_get_versions(auth_repo, *ROLES)
    assert versions_after["targets"] == versions_before["targets"]
    assert versions_after["snapshot"] > versions_before["snapshot"]
    assert versions_after["timestamp"] > versions_before["timestamp"]


def test_key_management_context_with_key_pin_loads_role_key_from_non_signature_slot(
    make_fake_yubikey, keystore, create_auth_repo, tmp_path, block_reprompt, monkeypatch
):
    make_fake_yubikey("root2", extra_slots={SLOT.AUTHENTICATION: "targets"})
    auth_repo = create_auth_repo()

    def _unexpected_pin_prompt(*_args, **_kwargs):
        raise AssertionError("unexpected PIN prompt: --key-pin was not bound")

    monkeypatch.setattr(taf.utils, "getpass", _unexpected_pin_prompt)

    with key_management_context(
        roles=["targets"],
        path=str(auth_repo.path),
        key_pin=VALID_PIN,
        keystore=str(write_signing_keystore(tmp_path, keystore, names=())),
    ) as auth_repo:
        assert auth_repo.check_if_keys_loaded("targets")
        loaded_keyids = set(auth_repo.signer_cache["targets"])

    expected_keyid = load_signer_from_file(keystore / "targets").public_key.keyid
    assert loaded_keyids == {expected_keyid}
