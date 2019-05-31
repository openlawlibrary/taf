import pytest
from taf.sc_utils import is_valid_metadata_yubikey

import oll_sc.exceptions


def test_check_no_key_inserted_for_targets_should_raise_error(taf_happy_path, targets_yk):
  with pytest.raises(oll_sc.exceptions.SmartCardNotPresentError):
    if targets_yk.is_inserted():
      targets_yk.remove()
    assert is_valid_metadata_yubikey(taf_happy_path, 'targets', (1,), '123456')


def test_check_targets_key_id_for_targets_should_return_true(taf_happy_path, targets_yk):
  targets_yk.insert()
  assert is_valid_metadata_yubikey(taf_happy_path, 'targets', (1,), '123456')


def test_check_targets_key_id_for_targets_with_wrong_pin_should_raise_error(taf_happy_path, targets_yk):
  with pytest.raises(oll_sc.exceptions.SmartCardWrongPinError):
    targets_yk.insert()
    assert is_valid_metadata_yubikey(taf_happy_path, 'targets', (1,), 'wrong pin')


def test_check_root_key_id_for_targets_should_return_false(taf_happy_path, root1_yk):
  root1_yk.insert()
  assert not is_valid_metadata_yubikey(taf_happy_path, 'targets', (1,), '123456')
