import datetime
from pathlib import Path

import pytest
import securesystemslib
import taf.exceptions
from taf.api import update_timestamp
from taf.utils import to_tuf_datetime_format

import tuf


def test_update_timestamp_valid_key(taf_happy_path, timestamp_key):
  start_date = datetime.datetime.now()
  interval = 1
  expected_expiration_date = to_tuf_datetime_format(start_date, interval)

  update_timestamp(taf_happy_path, timestamp_key, start_date, interval)
  new_timestamp_metadata = str(Path(taf_happy_path.metadata_staged_path) / 'timestamp.json')
  signable = securesystemslib.util.load_json_file(new_timestamp_metadata)
  tuf.formats.SIGNABLE_SCHEMA.check_match(signable)
  actual_expiration_date = signable['signed']['expires']

  assert actual_expiration_date == expected_expiration_date


def test_update_timestamp_wrong_key(taf_happy_path, snapshot_key):
  with pytest.raises(taf.exceptions.InvalidKeyError):
    update_timestamp(taf_happy_path, snapshot_key)


def test_update_targets_valid_key_valid_pin(taf_happy_path, targets_yk):
  pass


def test_update_targets_valid_key_wrong_pin(taf_happy_path, targets_yk):
  pass


def test_update_targets_wrong_key(taf_happy_path, root1_yk):
  pass
