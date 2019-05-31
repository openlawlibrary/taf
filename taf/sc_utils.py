import securesystemslib.formats

from oll_sc.api import sc_export_pub_key_pem
from tuf.repository_tool import import_rsakey_from_pem


def get_yubikey_public_key(key_slot, pin):
  """Return public key from a smart card in TUF's RSAKEY_SCHEMA format.

  Args:
    - key_slot(tuple): Key ID as tuple (e.g. (1,))
    - pin(str): Pin for session login

  Returns:
    A dictionary containing the RSA keys and other identifying information
    from inserted smart card.
    Conforms to 'securesystemslib.formats.RSAKEY_SCHEMA'.

  Raises:
    - SmartCardNotPresentError: If smart card is not inserted
    - SmartCardWrongPinError: If pin is incorrect
    - SmartCardFindKeyObjectError: If public key for given key id does not exist
    - securesystemslib.exceptions.FormatError: if 'PEM' is improperly formatted.
  """
  pub_key_pem = sc_export_pub_key_pem(key_slot, pin).decode('utf-8')
  return import_rsakey_from_pem(pub_key_pem)


def is_valid_metadata_key(repository, role, key):
  """Checks if metadata role contains key id of provided key.

  Args:
    - repository(taf.repository_tool.Repository): TAF repository
    - role(str): Metadata role
    - key(securesystemslib.formats.RSAKEY_SCHEMA): Timestamp key.

  Returns:
    Boolean. True if key id is in metadata role key ids, False otherwise.

  Raises:
    - securesystemslib.exceptions.FormatError: If key does not match RSAKEY_SCHEMA
    - securesystemslib.exceptions.UnknownRoleError: If role does not exist
  """
  securesystemslib.formats.RSAKEY_SCHEMA.check_match(key)

  return key['keyid'] in repository.get_role_keys(role)


def is_valid_metadata_yubikey(repository, role, key_slot, pin):
  """Checks if metadata role contains key id from YubiKey.

  Args:
    - repository(taf.repository_tool.Repository): TAF repository
    - role(str): Metadata role
    - key_slot(tuple): Key ID as tuple (e.g. (1,))
    - pin(str): Pin for session login

  Returns:
    Boolean. True if smart card key id belongs to metadata role key ids

  Raises:
    - SmartCardNotPresentError: If smart card is not inserted
    - SmartCardWrongPinError: If pin is incorrect
    - SmartCardFindKeyObjectError: If public key for given key id does not exist
    - securesystemslib.exceptions.FormatError: If 'PEM' is improperly formatted.
    - securesystemslib.exceptions.UnknownRoleError: If role does not exist
  """
  securesystemslib.formats.ROLENAME_SCHEMA.check_match(role)

  public_key = get_yubikey_public_key(key_slot, pin)
  return is_valid_metadata_key(repository, role, public_key)
