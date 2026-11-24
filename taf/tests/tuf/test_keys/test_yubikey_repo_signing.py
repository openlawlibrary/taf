import pytest
from yubikit.piv import SLOT

import taf.utils
from taf.api.api_workflow import key_management_context
from taf.api.metadata import update_snapshot_and_timestamp
from taf.tests.conftest import (
    create_authentication_repository,
    keys_description_of_scheme,
)
from taf.tests.tuf.test_keys.conftest import (
    pin_manager_for,
    sign_target_update,
    verify_and_get_versions,
)
from taf.tools.yubikey.yubikey_utils import VALID_PIN
from taf.tuf.signer_uris import create_signer_from_keystore_file
from taf.constants import DEFAULT_RSA_SIGNATURE_SCHEME

ROLES = ("targets", "snapshot", "timestamp")


def test_create_repo_and_sign_target_update_across_devices_and_slots(
    make_fake_yubikey, empty_keystore, create_auth_repo
):
    device_b = make_fake_yubikey("targets")
    device_a = make_fake_yubikey(
        "snapshot", extra_slots={SLOT.AUTHENTICATION: "timestamp"}
    )
    auth_repo = create_auth_repo(pin_manager_for(device_a, device_b))
    versions_before = verify_and_get_versions(auth_repo, *ROLES)

    sign_target_update(auth_repo, empty_keystore)

    versions_after = verify_and_get_versions(auth_repo, *ROLES)
    for role in ROLES:
        assert versions_after[role] > versions_before[role]


def test_sign_target_update_with_every_role_in_its_own_slot_of_one_device(
    make_fake_yubikey, empty_keystore, create_auth_repo
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

    sign_target_update(auth_repo, empty_keystore)

    versions_after = verify_and_get_versions(auth_repo, *ROLES)
    for role in ROLES:
        assert versions_after[role] > versions_before[role]


@pytest.mark.parametrize("split_across_devices", [False, True])
def test_update_snapshot_and_timestamp_signs_with_keys_in_non_signature_slots(
    make_fake_yubikey, empty_keystore, create_auth_repo, split_across_devices
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
        keystore=str(empty_keystore),
        roles_to_sync=["targets"],
        commit_msg="Update snapshot and timestamp",
        push=False,
    )

    versions_after = verify_and_get_versions(auth_repo, *ROLES)
    assert versions_after["targets"] == versions_before["targets"]
    assert versions_after["snapshot"] > versions_before["snapshot"]
    assert versions_after["timestamp"] > versions_before["timestamp"]


def test_key_management_context_with_key_pin_loads_role_key_from_non_signature_slot(
    make_fake_yubikey,
    keystore,
    empty_keystore,
    create_auth_repo,
    block_reprompt,
    monkeypatch,
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
        keystore=str(empty_keystore),
    ) as auth_repo:
        assert auth_repo.check_if_keys_loaded("targets")
        loaded_keyids = set(auth_repo.signer_cache["targets"])

    expected_keyid = create_signer_from_keystore_file(
        keystore, "targets", DEFAULT_RSA_SIGNATURE_SCHEME
    ).public_key.keyid
    assert loaded_keyids == {expected_keyid}


def test_sign_target_update_with_rsa_pss_key_on_yubikey(
    make_fake_yubikey,
    keystore_of_scheme,
    keystore_rsassa_pss_sha256_snapshot_timestamp,
    repo_path,
):
    scheme = "rsassa-pss-sha256"
    keystore = keystore_of_scheme(scheme)
    device = make_fake_yubikey("targets", keystore_path=keystore, scheme=scheme)
    auth_repo = create_authentication_repository(
        repo_path,
        pin_manager_for(device),
        "test/auth",
        keys_description_of_scheme(scheme),
        keystore=keystore,
    )
    versions_before = verify_and_get_versions(auth_repo, *ROLES)

    sign_target_update(auth_repo, keystore_rsassa_pss_sha256_snapshot_timestamp)

    versions_after = verify_and_get_versions(auth_repo, *ROLES)
    for role in ROLES:
        assert versions_after[role] > versions_before[role]
