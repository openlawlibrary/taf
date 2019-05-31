import datetime

from securesystemslib.exceptions import Error as SSLibError

from oll_sc.exceptions import SmartCardError
from tuf.exceptions import Error as TUFError

from .exceptions import (InvalidKeyError, TargetsMetadataUpdateError,
                         TimestampMetadataUpdateError)
from .sc_utils import (get_yubikey_public_key, is_valid_metadata_key,
                       is_valid_metadata_yubikey)


def update_targets(repository, targets_data, date, targets_key_slot, targets_key_pin):
  """Update target data, sign with smart card and write.

  Args:
    - repository(taf.repository_tool.Repository): TAF repository
    - targets_data(dict): Dictionary with targets data
    - date(datetime): Build date
    - targets_key_slot(tuple): Slot with key on a smart card used for signing
    - targets_key_pin(str): Targets key pin

  Returns:
    None

  Raises:
    - InvalidKeyError: If wrong key is used to sign metadata
    - MetadataUpdateError: If any other error happened during metadata update
    - SmartCardError: If PIN is wrong or smart card is not inserted, or can't perform signing, ...
  """
  try:
    if not is_valid_metadata_yubikey(repository, 'targets', targets_key_slot, targets_key_pin):
      raise InvalidKeyError('targets')

    pub_key = get_yubikey_public_key(targets_key_slot, targets_key_pin)

    repository.add_targets(targets_data)
    repository.set_metadata_expiration_date('targets', date)
    repository.write_targets_metadata(pub_key, targets_key_slot, targets_key_pin)

  except (TUFError, SSLibError) as e:
    raise TargetsMetadataUpdateError(str(e))


def update_timestamp(repository, timestamp_key,
                     start_date=datetime.datetime.now(), interval=None):
  """Update timestamp periodically.

  Args:
    - repository(taf.repository_tool.Repository): TAF repository
    - timestamp_key(securesystemslib.formats.RSAKEY_SCHEMA): Timestamp key.
    - start_date(datetime): Date to which the specified interval is added when
                            calculating expiration date. If a value is not
                            provided, it is set to the current time
    - interval(int): A number of days added to the start date. If not provided,
                     the default value is used

  Returns:
    None

  Raises:
    - InvalidKeyError: If wrong key is used to sign metadata
    - TimestampMetadataUpdateError: If any other error happened during metadata update
  """
  try:
    if not is_valid_metadata_key(repository, 'timestamp', timestamp_key):
      raise InvalidKeyError('targets')

    repository.set_metadata_expiration_date('timestamp', start_date, interval)
    repository.write_timestamp_metadata(timestamp_key)

  except (SmartCardError, TUFError, SSLibError) as e:
    raise TimestampMetadataUpdateError(str(e))
