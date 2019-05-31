import datetime

from securesystemslib.exceptions import Error as SSLibError

from oll_sc.exceptions import SmartCardError
from tuf.exceptions import Error as TUFError

from .exceptions import (InvalidKeyError, TargetsMetadataUpdateError,
                         TimestampMetadataUpdateError)
from .sc_utils import is_valid_metadata_key, is_valid_metadata_yubikey


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
  """
  try:
    if not is_valid_metadata_yubikey(repository, 'targets', targets_key_slot, targets_key_pin):
      raise InvalidKeyError('targets')

    repository.add_targets(targets_data)
    repository.set_metadata_expiration_date('targets', date)
    repository.write_targets_metadata(targets_key_slot, targets_key_pin)
  except (SmartCardError, TUFError, SSLibError) as e:
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
    - securesystemslib.exceptions.FormatError: if 'PEM' is improperly formatted.
  """
  try:
    if not is_valid_metadata_key(repository, 'timestamp', timestamp_key):
      raise InvalidKeyError('targets')

    repository.set_metadata_expiration_date('timestamp', start_date, interval)
    repository.write_timestamp_metadata(timestamp_key)

  except (SmartCardError, TUFError, SSLibError) as e:
    raise TimestampMetadataUpdateError(str(e))
