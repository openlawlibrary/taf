from taf.api import check_inserted_targets_key_id


def test_check_inserted_targets_key_id(taf_happy_path):
  # TODO: Mock pkcs11 to use keys from keystore
  assert check_inserted_targets_key_id(taf_happy_path, (1,), '123456')
