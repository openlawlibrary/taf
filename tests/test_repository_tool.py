import datetime
from pathlib import Path

import pytest
import securesystemslib

import oll_sc.exceptions
import taf.exceptions
import tuf
from taf.utils import to_tuf_datetime_format


def test_update_snapshot_and_timestmap(taf_happy_path, keystore):
  date_now = datetime.datetime.now()
  snapshot_date = date_now + datetime.timedelta(1)
  snapshot_interval = 2
  timestamp_date = date_now + datetime.timedelta(2)
  timestamp_interval = 3

  kwargs = {
      'snapshot_date': snapshot_date,
      'timestamp_date': timestamp_date,
      'snapshot_interval': snapshot_interval,
      'timestamp_interval': timestamp_interval
  }

  taf_happy_path.update_snapshot_and_timestmap(keystore, **kwargs)

  old_targets_metadata = Path(taf_happy_path.metadata_path) / 'targets.json'
  new_targets_metadata = Path(taf_happy_path.metadata_staged_path) / 'targets.json'
  new_snapshot_metadata = str(Path(taf_happy_path.metadata_staged_path) / 'snapshot.json')
  new_timestamp_metadata = str(Path(taf_happy_path.metadata_staged_path) / 'timestamp.json')

  def check_expiration_date(metadata, date, interval):
    signable = securesystemslib.util.load_json_file(metadata)
    tuf.formats.SIGNABLE_SCHEMA.check_match(signable)
    actual_expiration_date = signable['signed']['expires']

    assert actual_expiration_date == to_tuf_datetime_format(date, interval)

  check_expiration_date(new_snapshot_metadata, snapshot_date, snapshot_interval)
  check_expiration_date(new_timestamp_metadata, timestamp_date, timestamp_interval)

  # Targets data should remain the same
  assert old_targets_metadata.read_bytes() == new_targets_metadata.read_bytes()


def test_update_snapshot_valid_key(taf_happy_path, snapshot_key):
  start_date = datetime.datetime.now()
  interval = 1
  expected_expiration_date = to_tuf_datetime_format(start_date, interval)

  taf_happy_path.update_snapshot(snapshot_key, start_date, interval)
  new_snapshot_metadata = str(Path(taf_happy_path.metadata_staged_path) / 'snapshot.json')
  signable = securesystemslib.util.load_json_file(new_snapshot_metadata)
  tuf.formats.SIGNABLE_SCHEMA.check_match(signable)
  actual_expiration_date = signable['signed']['expires']

  assert actual_expiration_date == expected_expiration_date


def test_update_snapshot_wrong_key(taf_happy_path, timestamp_key):
  with pytest.raises(taf.exceptions.InvalidKeyError):
    taf_happy_path.update_snapshot(timestamp_key)


def test_update_timestamp_valid_key(taf_happy_path, timestamp_key):
  start_date = datetime.datetime.now()
  interval = 1
  expected_expiration_date = to_tuf_datetime_format(start_date, interval)

  taf_happy_path.update_timestamp(timestamp_key, start_date, interval)
  new_timestamp_metadata = str(Path(taf_happy_path.metadata_staged_path) / 'timestamp.json')
  signable = securesystemslib.util.load_json_file(new_timestamp_metadata)
  tuf.formats.SIGNABLE_SCHEMA.check_match(signable)
  actual_expiration_date = signable['signed']['expires']

  assert actual_expiration_date == expected_expiration_date


def test_update_timestamp_wrong_key(taf_happy_path, snapshot_key):
  with pytest.raises(taf.exceptions.InvalidKeyError):
    taf_happy_path.update_timestamp(snapshot_key)


def test_update_targets_valid_key_valid_pin(taf_happy_path, targets_yk):
  targets_path = Path(taf_happy_path.targets_path)
  repositories_json_path = targets_path / 'repositories.json'

  branch_id = '14e81cd1-0050-43aa-9e2c-e34fffa6f517'
  target_commit_sha = 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx'
  repositories_json_old = repositories_json_path.read_text()

  targets_data = {
      'branch': {
          'target': branch_id,
      },
      'dummy/target_dummy_repo': {
          'target': {
              'commit': target_commit_sha
          }
      },
      'capstone': {}
  }

  targets_yk.insert()
  taf_happy_path.update_targets((1, ), '123456', targets_data, datetime.datetime.now())

  assert (targets_path / 'branch').read_text() == branch_id
  assert target_commit_sha in (targets_path / 'dummy/target_dummy_repo').read_text()
  assert (targets_path / 'capstone').is_file()
  assert repositories_json_old == repositories_json_path.read_text()


def test_update_targets_valid_key_wrong_pin(taf_happy_path, targets_yk):
  with pytest.raises(oll_sc.exceptions.SmartCardWrongPinError):
    targets_yk.insert()
    taf_happy_path.update_targets((1, ), '123')


def test_update_targets_wrong_key(taf_happy_path, root1_yk):
  with pytest.raises(taf.exceptions.InvalidKeyError):
    root1_yk.insert()
    taf_happy_path.update_targets((1, ), '123456')
