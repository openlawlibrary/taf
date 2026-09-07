import json
import shutil

from tuf.api.metadata import Metadata
from yubikit.piv import SLOT

from taf.api.repository import create_repository
from taf.api.targets import register_target_files
from taf.auth_repo import AuthenticationRepository
from taf.yubikey.yubikey_manager import PinManager


def test_create_repo_and_sign_target_update_across_devices_and_slots(
    make_fake_yubikey, keystore, tmp_path
):
    # root/targets/snapshot/timestamp are plain keystore roles for repo
    # creation - pre-populating their key files means every load succeeds
    # on the first try, so no interactive prompting is needed. The same
    # key material is then flashed onto the fake YubiKeys below, so the
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

    device_b = make_fake_yubikey("targets")
    device_a = make_fake_yubikey(
        "snapshot", extra_slots={SLOT.AUTHENTICATION: "timestamp"}
    )

    pin_manager = PinManager()
    pin_manager.add_pin(device_a.serial, device_a.pin)
    pin_manager.add_pin(device_b.serial, device_b.pin)

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
        pin_manager,
        keystore=str(creation_keystore),
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

    # add a target file and sign the update using the YubiKeys - an empty
    # keystore dir means load_signers finds no matching keystore file and
    # falls through to _load_yubikeys, discovering the inserted devices
    auth_repo = AuthenticationRepository(path=str(repo_path), pin_manager=pin_manager)
    target_file = auth_repo.targets_path / "a-new-target.txt"
    target_file.write_text("hello")

    signing_keystore = tmp_path / "signing_keystore"
    signing_keystore.mkdir()

    register_target_files(
        str(repo_path),
        pin_manager,
        keystore=str(signing_keystore),
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
