from securesystemslib.keys import _get_keyid

from oll_sc.api import sc_export_pub_key_pem


def sc_get_tuf_key_id(key_id, pin):
  """Return key id used by TUF.
  NOTE: This function uses `securesystemslib.keys._get_keyid` to hash smart
        card's public key.
  """
  pub_key_pem = sc_export_pub_key_pem(key_id, pin)
  return _get_keyid('rsa', 'rsassa-pss-sha256', dict(
      public=pub_key_pem.decode('utf-8').rstrip()
  ))


def check_inserted_key_id(repository, role, key_id, pin):
  """Check if inserted smart card's private key id is same as TAF's key id."""
  sc_key_id = sc_get_tuf_key_id(key_id, pin)
  return sc_key_id in repository.get_role_keys(role)
