import datetime
from pathlib import Path

import pytest
import securesystemslib
import tuf

import taf.exceptions
import taf.yubikey as yk
from taf.constants import DEFAULT_RSA_SIGNATURE_SCHEME
from taf.tests import TEST_WITH_REAL_YK
from taf.tests.yubikey_utils import VALID_PIN
from taf.utils import to_tuf_datetime_format


@pytest.mark.skipif(TEST_WITH_REAL_YK, reason="Testing with real Yubikey.")
def test_check_no_key_inserted_for_targets_should_raise_error(repositories, targets_yk):
    taf_happy_path = repositories["test-happy-path"]
    targets_yk.insert()
    targets_yk.remove()
    with pytest.raises(taf.exceptions.YubikeyError):
        taf_happy_path.is_valid_metadata_yubikey("targets")


def test_check_targets_key_id_for_targets_should_return_true(repositories, targets_yk):
    taf_happy_path = repositories["test-happy-path"]
    targets_yk.insert()
    assert taf_happy_path.is_valid_metadata_yubikey("targets", targets_yk.tuf_key)


def test_check_root_key_id_for_targets_should_return_false(repositories, root1_yk):
    taf_happy_path = repositories["test-happy-path"]
    root1_yk.insert()
    assert not taf_happy_path.is_valid_metadata_yubikey("targets", root1_yk.tuf_key)


def test_update_snapshot_valid_key(repositories, snapshot_key):
    taf_happy_path = repositories["test-happy-path"]
    start_date = datetime.datetime.now()
    interval = 1
    expected_expiration_date = to_tuf_datetime_format(start_date, interval)
    targets_metadata_path = Path(taf_happy_path.metadata_path) / "targets.json"
    old_targets_metadata = targets_metadata_path.read_bytes()
    taf_happy_path.update_snapshot_keystores(
        [snapshot_key], start_date=start_date, interval=interval
    )
    new_snapshot_metadata = str(Path(taf_happy_path.metadata_path) / "snapshot.json")
    signable = securesystemslib.util.load_json_file(new_snapshot_metadata)
    tuf.formats.SIGNABLE_SCHEMA.check_match(signable)
    actual_expiration_date = signable["signed"]["expires"]

    # Targets data should remain the same
    assert old_targets_metadata == targets_metadata_path.read_bytes()
    assert actual_expiration_date == expected_expiration_date


def test_update_snapshot_wrong_key(repositories, timestamp_key):
    taf_happy_path = repositories["test-happy-path"]
    with pytest.raises(taf.exceptions.InvalidKeyError):
        taf_happy_path.update_snapshot_keystores([timestamp_key])


def test_update_timestamp_valid_key(repositories, timestamp_key):
    taf_happy_path = repositories["test-happy-path"]
    start_date = datetime.datetime.now()
    interval = 1
    expected_expiration_date = to_tuf_datetime_format(start_date, interval)
    targets_metadata_path = Path(taf_happy_path.metadata_path) / "targets.json"
    snapshot_metadata_path = Path(taf_happy_path.metadata_path) / "snapshot.json"
    old_targets_metadata = targets_metadata_path.read_bytes()
    old_snapshot_metadata = snapshot_metadata_path.read_bytes()
    taf_happy_path.update_timestamp_keystores(
        [timestamp_key], start_date=start_date, interval=interval
    )
    new_timestamp_metadata = str(Path(taf_happy_path.metadata_path) / "timestamp.json")
    signable = securesystemslib.util.load_json_file(new_timestamp_metadata)
    tuf.formats.SIGNABLE_SCHEMA.check_match(signable)
    actual_expiration_date = signable["signed"]["expires"]

    assert actual_expiration_date == expected_expiration_date
    # check if targets and snapshot remained the same
    assert old_targets_metadata == targets_metadata_path.read_bytes()
    assert old_snapshot_metadata == snapshot_metadata_path.read_bytes()


def test_update_timestamp_wrong_key(repositories, snapshot_key):
    taf_happy_path = repositories["test-happy-path"]
    with pytest.raises(taf.exceptions.InvalidKeyError):
        taf_happy_path.update_timestamp_keystores([snapshot_key])


def test_update_targets_from_keystore_valid_key(repositories, targets_key):
    taf_happy_path = repositories["test-happy-path"]
    targets_path = Path(taf_happy_path.targets_path)
    repositories_json_path = targets_path / "repositories.json"

    branch_id = "14e81cd1-0050-43aa-9e2c-e34fffa6f517"
    target_commit_sha = "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
    repositories_json_old = repositories_json_path.read_text()

    targets_data = {
        "branch": {"target": branch_id},
        "dummy/target_dummy_repo": {"target": {"commit": target_commit_sha}},
        "test_file": {},
    }

    taf_happy_path.update_targets_keystores(
        [targets_key],
        added_targets_data=targets_data,
        start_date=datetime.datetime.now(),
    )

    assert (targets_path / "branch").read_text() == branch_id
    assert target_commit_sha in (targets_path / "dummy/target_dummy_repo").read_text()
    assert (targets_path / "test_file").is_file()
    assert repositories_json_old == repositories_json_path.read_text()


def test_update_targets_from_keystore_wrong_key(repositories, snapshot_key):
    taf_happy_path = repositories["test-happy-path"]
    targets_data = {"test_file": {}}

    with pytest.raises(taf.exceptions.TargetsMetadataUpdateError):
        taf_happy_path.update_targets_keystores([snapshot_key], targets_data)


def test_update_targets_valid_key_valid_pin(repositories, targets_yk):
    taf_happy_path = repositories["test-happy-path"]
    if targets_yk.scheme != DEFAULT_RSA_SIGNATURE_SCHEME:
        pytest.skip()
    targets_path = Path(taf_happy_path.targets_path)
    repositories_json_path = targets_path / "repositories.json"

    branch_id = "14e81cd1-0050-43aa-9e2c-e34fffa6f517"
    target_commit_sha = "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
    repositories_json_old = repositories_json_path.read_text()

    targets_data = {
        "branch": {"target": branch_id},
        "dummy/target_dummy_repo": {"target": {"commit": target_commit_sha}},
        "test_file": {},
    }
    yk.add_key_pin(targets_yk.serial, VALID_PIN)
    targets_yk.insert()
    public_key = targets_yk.tuf_key
    taf_happy_path.update_targets_yubikeys(
        [public_key],
        added_targets_data=targets_data,
        start_date=datetime.datetime.now(),
    )

    assert (targets_path / "branch").read_text() == branch_id
    assert target_commit_sha in (targets_path / "dummy/target_dummy_repo").read_text()
    assert (targets_path / "test_file").is_file()
    assert repositories_json_old == repositories_json_path.read_text()


def test_delete_target_file_valid_key_valid_pin(repositories, targets_yk):
    taf_happy_path = repositories["test-happy-path"]
    if targets_yk.scheme != DEFAULT_RSA_SIGNATURE_SCHEME:
        pytest.skip()
    targets_path = Path(taf_happy_path.targets_path)

    yk.add_key_pin(targets_yk.serial, VALID_PIN)
    targets_yk.insert()
    public_key = targets_yk.tuf_key

    # add test_file
    targets_data = {"test_file": {}}
    taf_happy_path.update_targets_yubikeys(
        [public_key],
        added_targets_data=targets_data,
        start_date=datetime.datetime.now(),
    )

    assert (targets_path / "test_file").is_file()
    targets_obj = taf_happy_path._role_obj("targets")
    assert "test_file" in targets_obj.target_files

    # remove test_file
    taf_happy_path.update_targets_yubikeys(
        [public_key],
        removed_targets_data=targets_data,
        start_date=datetime.datetime.now(),
    )

    assert not (targets_path / "test_file").is_file()
    targets_obj = taf_happy_path._role_obj("targets")
    assert "test_file" not in targets_obj.target_files


@pytest.mark.skipif(TEST_WITH_REAL_YK, reason="Testing with real Yubikey.")
def test_update_targets_wrong_key(repositories, root1_yk):
    taf_happy_path = repositories["test-happy-path"]
    targets_data = {"test_file": {}}

    with pytest.raises(taf.exceptions.TargetsMetadataUpdateError):
        root1_yk.insert()
        yk.add_key_pin(root1_yk.serial, VALID_PIN)
        taf_happy_path.update_targets_yubikeys(
            [root1_yk.tuf_key], added_targets_data=targets_data
        )
