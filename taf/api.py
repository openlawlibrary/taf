from oll_sc.api import sc_export_pub_key_pem
from tuf.repository_tool import import_rsakey_from_pem


def sc_get_public_key(key_slot, pin):
  """Return public key from a smart card.

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


def check_inserted_key_id(repository, role, key_slot, pin):
  """Return public key from a smart card.

  Args:
    - key_slot(tuple): Key ID as tuple (e.g. (1,))
    - pin(str): Pin for session login

  Returns:
    Boolean. True if smart card key id belongs to metadata role key ids

  Raises:
    - SmartCardNotPresentError: If smart card is not inserted
    - SmartCardWrongPinError: If pin is incorrect
    - SmartCardFindKeyObjectError: If public key for given key id does not exist
    - securesystemslib.exceptions.FormatError: if 'PEM' is improperly formatted.
  """
  public_key = sc_get_public_key(key_slot, pin)
  return public_key['keyid'] in repository.get_role_keys(role)
