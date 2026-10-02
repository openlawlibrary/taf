import json
import shutil

import pytest
from tuf.api.metadata import Metadata
from yubikit.piv import SLOT

import taf.utils
from taf.api.api_workflow import key_management_context
from taf.api.metadata import update_snapshot_and_timestamp
from taf.api.repository import create_repository
from taf.api.targets import register_target_files
from taf.auth_repo import AuthenticationRepository
from taf.tests.tuf.test_keys.conftest import write_target
from taf.tools.yubikey.yubikey_utils import VALID_PIN
from taf.tuf.keys import load_signer_from_file
from taf.yubikey.yubikey_manager import PinManager


def _create_repo(keystore, tmp_path):
    # root/targets/snapshot/timestamp are plain keystore roles for repo
    # creation - pre-populating their key files means every load succeeds
    # on the first try, so no interactive prompting is needed. The same
    # key material is flashed onto fake YubiKeys by each test, so the
    # roles can be re-signed via YubiKey afterwards.
    creation_keystore = tmp_path / "creation_keystore"
    creation_keystore.mkdir()
    for src_name, dst_name in [
        ("root1", "root"),
        ("targets", "targets"),
        ("snapshot", "snapshot"),
        ("timestamp", "timestamp"),
    ]:
        shutil.copy(keystore / src_name, creation_keystore / dst_name)
        shutil.copy(keystore / f"{src_name}.pub", creation_keystore / f"{dst_name}.pub")

    repo_path = tmp_path / "auth"
    roles_key_infos_path = tmp_path / "keys-description.json"
    roles_key_infos_path.write_text(
        json.dumps(
            {
                "roles": {
                    "root": {"number": 1, "threshold": 1},
                    "targets": {"number": 1, "threshold": 1},
                    "snapshot": {"number": 1, "threshold": 1},
                    "timestamp": {},
                }
            }
        )
    )

    create_repository(
        str(repo_path),
        PinManager(),
        keystore=str(creation_keystore),
        roles_key_infos=str(roles_key_infos_path),
        commit=True,
        test=True,
    )
    return repo_path


def _empty_keystore(tmp_path):
    # an empty keystore dir means load_signers finds no matching keystore
    # file and falls through to _load_yubikeys, discovering the inserted
    # devices
    signing_keystore = tmp_path / "signing_keystore"
    signing_keystore.mkdir()
    return signing_keystore


def _pin_manager(*devices):
    pin_manager = PinManager()
    for device in devices:
        pin_manager.add_pin(device.serial, device.pin)
    return pin_manager


def _read_metadata(repo_path, *roles):
    metadata_path = repo_path / "metadata"
    return {
        role: Metadata.from_file(str(metadata_path / f"{role}.json"))
        for role in ("root",) + roles
    }


def _verify_and_get_versions(repo_path, *roles):
    metadata = _read_metadata(repo_path, *roles)
    for role in roles:
        metadata["root"].verify_delegate(role, metadata[role])
    return {role: metadata[role].signed.version for role in roles}


def _sign_target_update(repo_path, pin_manager, signing_keystore):
    target_file = repo_path / "targets" / "a-new-target.txt"
    write_target(target_file)
    register_target_files(
        str(repo_path),
        pin_manager,
        keystore=str(signing_keystore),
        update_snapshot_and_timestamp=True,
        push=False,
    )
    auth_repo = AuthenticationRepository(path=str(repo_path), pin_manager=pin_manager)
    assert "a-new-target.txt" in auth_repo.get_signed_target_files()


def test_create_repo_and_sign_target_update_across_devices_and_slots(
    make_fake_yubikey, keystore, tmp_path
):
    device_b = make_fake_yubikey("targets")
    device_a = make_fake_yubikey(
        "snapshot", extra_slots={SLOT.AUTHENTICATION: "timestamp"}
    )

    repo_path = _create_repo(keystore, tmp_path)
    roles = ("targets", "snapshot", "timestamp")
    versions_before = _verify_and_get_versions(repo_path, *roles)

    _sign_target_update(
        repo_path, _pin_manager(device_a, device_b), _empty_keystore(tmp_path)
    )

    versions_after = _verify_and_get_versions(repo_path, *roles)
    for role in roles:
        assert versions_after[role] > versions_before[role]


def test_sign_target_update_with_every_role_in_its_own_slot_of_one_device(
    make_fake_yubikey, keystore, tmp_path
):
    device = make_fake_yubikey(
        "targets",
        extra_slots={
            SLOT.AUTHENTICATION: "snapshot",
            SLOT.KEY_MANAGEMENT: "timestamp",
        },
    )

    repo_path = _create_repo(keystore, tmp_path)
    roles = ("targets", "snapshot", "timestamp")
    versions_before = _verify_and_get_versions(repo_path, *roles)

    _sign_target_update(repo_path, _pin_manager(device), _empty_keystore(tmp_path))

    versions_after = _verify_and_get_versions(repo_path, *roles)
    for role in roles:
        assert versions_after[role] > versions_before[role]


@pytest.mark.parametrize("split_across_devices", [False, True])
def test_update_snapshot_and_timestamp_signs_with_keys_in_non_signature_slots(
    make_fake_yubikey, keystore, tmp_path, split_across_devices
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

    repo_path = _create_repo(keystore, tmp_path)
    versions_before = _verify_and_get_versions(
        repo_path, "targets", "snapshot", "timestamp"
    )

    update_snapshot_and_timestamp(
        str(repo_path),
        _pin_manager(*devices),
        keystore=str(_empty_keystore(tmp_path)),
        roles_to_sync=["targets"],
        commit_msg="Update snapshot and timestamp",
        push=False,
    )

    versions_after = _verify_and_get_versions(
        repo_path, "targets", "snapshot", "timestamp"
    )
    assert versions_after["targets"] == versions_before["targets"]
    assert versions_after["snapshot"] > versions_before["snapshot"]
    assert versions_after["timestamp"] > versions_before["timestamp"]


def test_key_management_context_with_key_pin_loads_role_key_from_non_signature_slot(
    make_fake_yubikey, keystore, tmp_path, block_reprompt, monkeypatch
):
    make_fake_yubikey("root2", extra_slots={SLOT.AUTHENTICATION: "targets"})
    repo_path = _create_repo(keystore, tmp_path)

    def _unexpected_pin_prompt(*_args, **_kwargs):
        raise AssertionError("unexpected PIN prompt: --key-pin was not bound")

    monkeypatch.setattr(taf.utils, "getpass", _unexpected_pin_prompt)

    with key_management_context(
        roles=["targets"],
        path=str(repo_path),
        key_pin=VALID_PIN,
        keystore=str(_empty_keystore(tmp_path)),
    ) as auth_repo:
        assert auth_repo.check_if_keys_loaded("targets")
        loaded_keyids = set(auth_repo.signer_cache["targets"])

    expected_keyid = load_signer_from_file(keystore / "targets").public_key.keyid
    assert loaded_keyids == {expected_keyid}
