import datetime
from pathlib import Path

import pytest
import securesystemslib
import taf.exceptions
import tuf
from taf.tests import TEST_WITH_REAL_YK
from taf.utils import to_tuf_datetime_format


@pytest.mark.skipif(TEST_WITH_REAL_YK, reason="Testing with real Yubikey.")
def test_check_no_key_inserted_for_targets_should_raise_error(
    taf_happy_path, targets_yk
):
    targets_yk.insert()
    targets_yk.remove()
    with pytest.raises(taf.exceptions.YubikeyError):
        taf_happy_path.is_valid_metadata_yubikey("targets")


def test_check_targets_key_id_for_targets_should_return_true(
    taf_happy_path, targets_yk
):
    targets_yk.insert()
    assert taf_happy_path.is_valid_metadata_yubikey("targets", targets_yk.tuf_key)


def test_check_root_key_id_for_targets_should_return_false(taf_happy_path, root1_yk):
    root1_yk.insert()
    assert not taf_happy_path.is_valid_metadata_yubikey("targets", root1_yk.tuf_key)


def test_update_snapshot_and_timestmap(taf_happy_path, snapshot_key, timestamp_key):
    date_now = datetime.datetime.now()
    snapshot_date = date_now + datetime.timedelta(1)
    snapshot_interval = 2
    timestamp_date = date_now + datetime.timedelta(2)
    timestamp_interval = 3

    kwargs = {
        "snapshot_date": snapshot_date,
        "timestamp_date": timestamp_date,
        "snapshot_interval": snapshot_interval,
        "timestamp_interval": timestamp_interval,
    }

    taf_happy_path.update_snapshot_and_timestmap(snapshot_key, timestamp_key, **kwargs)

    targets_metadata_path = Path(taf_happy_path.metadata_path) / "targets.json"
    snapshot_metadata_path = Path(taf_happy_path.metadata_path) / "snapshot.json"
    timestamp_metadata_path = Path(taf_happy_path.metadata_path) / "timestamp.json"

    old_targets_metadata = targets_metadata_path.read_bytes()

    def check_expiration_date(metadata_path, date, interval):
        signable = securesystemslib.util.load_json_file(metadata_path)
        tuf.formats.SIGNABLE_SCHEMA.check_match(signable)
        actual_expiration_date = signable["signed"]["expires"]

        assert actual_expiration_date == to_tuf_datetime_format(date, interval)

    check_expiration_date(str(snapshot_metadata_path), snapshot_date, snapshot_interval)
    check_expiration_date(
        str(timestamp_metadata_path), timestamp_date, timestamp_interval
    )

    # Targets data should remain the same
    assert old_targets_metadata == targets_metadata_path.read_bytes()


def test_update_snapshot_valid_key(taf_happy_path, snapshot_key):
    start_date = datetime.datetime.now()
    interval = 1
    expected_expiration_date = to_tuf_datetime_format(start_date, interval)
    taf_happy_path.update_snapshot(
        snapshot_key, start_date=start_date, interval=interval
    )
    new_snapshot_metadata = str(Path(taf_happy_path.metadata_path) / "snapshot.json")
    signable = securesystemslib.util.load_json_file(new_snapshot_metadata)
    tuf.formats.SIGNABLE_SCHEMA.check_match(signable)
    actual_expiration_date = signable["signed"]["expires"]

    assert actual_expiration_date == expected_expiration_date


def test_update_snapshot_wrong_key(taf_happy_path, timestamp_key):
    with pytest.raises(taf.exceptions.InvalidKeyError):
        taf_happy_path.update_snapshot(timestamp_key)


def test_update_timestamp_valid_key(taf_happy_path, timestamp_key):
    start_date = datetime.datetime.now()
    interval = 1
    expected_expiration_date = to_tuf_datetime_format(start_date, interval)

    taf_happy_path.update_timestamp(
        timestamp_key, start_date=start_date, interval=interval
    )
    new_timestamp_metadata = str(Path(taf_happy_path.metadata_path) / "timestamp.json")
    signable = securesystemslib.util.load_json_file(new_timestamp_metadata)
    tuf.formats.SIGNABLE_SCHEMA.check_match(signable)
    actual_expiration_date = signable["signed"]["expires"]

    assert actual_expiration_date == expected_expiration_date


def test_update_timestamp_wrong_key(taf_happy_path, snapshot_key):
    with pytest.raises(taf.exceptions.InvalidKeyError):
        taf_happy_path.update_timestamp(snapshot_key)


def test_update_targets_from_keystore_valid_key(taf_happy_path, targets_key):
    start_date = datetime.datetime.now()
    interval = 1
    expected_expiration_date = to_tuf_datetime_format(start_date, interval)

    taf_happy_path.update_targets_from_keystore(
        targets_key, start_date=start_date, interval=interval
    )
    new_targets_data = str(Path(taf_happy_path.metadata_path) / "targets.json")
    signable = securesystemslib.util.load_json_file(new_targets_data)
    tuf.formats.SIGNABLE_SCHEMA.check_match(signable)
    actual_expiration_date = signable["signed"]["expires"]

    assert actual_expiration_date == expected_expiration_date


def test_update_targets_from_keystore_wrong_key(taf_happy_path, snapshot_key):
    with pytest.raises(taf.exceptions.InvalidKeyError):
        taf_happy_path.update_targets_from_keystore(snapshot_key)


def test_update_targets_valid_key_valid_pin(taf_happy_path, targets_yk):
    targets_path = Path(taf_happy_path.targets_path)
    repositories_json_path = targets_path / "repositories.json"

    branch_id = "14e81cd1-0050-43aa-9e2c-e34fffa6f517"
    target_commit_sha = "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
    repositories_json_old = repositories_json_path.read_text()

    targets_data = {
        "branch": {"target": branch_id},
        "dummy/target_dummy_repo": {"target": {"commit": target_commit_sha}},
        "capstone": {},
    }

    targets_yk.insert()
    taf_happy_path.update_targets(
        "123456", targets_data, datetime.datetime.now(), public_key=targets_yk.tuf_key
    )

    assert (targets_path / "branch").read_text() == branch_id
    assert target_commit_sha in (targets_path / "dummy/target_dummy_repo").read_text()
    assert (targets_path / "capstone").is_file()
    assert repositories_json_old == repositories_json_path.read_text()


def test_update_targets_valid_key_wrong_pin(taf_happy_path, targets_yk):
    with pytest.raises(taf.exceptions.TargetsMetadataUpdateError):
        targets_yk.insert()
        taf_happy_path.update_targets("123", public_key=targets_yk.tuf_key)


@pytest.mark.skipif(TEST_WITH_REAL_YK, reason="Testing with real Yubikey.")
def test_update_targets_wrong_key(taf_happy_path, root1_yk):
    with pytest.raises(taf.exceptions.InvalidKeyError):
        root1_yk.insert()
        taf_happy_path.update_targets("123456")
