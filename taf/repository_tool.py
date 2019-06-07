import datetime
import json
import os
import shutil
from contextlib import contextmanager
from functools import partial
from pathlib import Path

import securesystemslib
from securesystemslib.exceptions import Error as SSLibError

from oll_sc.exceptions import SmartCardError
from taf.utils import normalize_file_line_endings
from tuf.exceptions import Error as TUFError
from tuf.repository_tool import (METADATA_DIRECTORY_NAME,
                                 METADATA_STAGED_DIRECTORY_NAME,
                                 TARGETS_DIRECTORY_NAME, import_rsakey_from_pem)

from .exceptions import (InvalidKeyError, MetadataUpdateError,
                         SnapshotMetadataUpdateError,
                         TargetsMetadataUpdateError,
                         TimestampMetadataUpdateError)

# Default expiration intervals per role
expiration_intervals = {
    'root': 365,
    'targets': 90,
    'snapshot': 7,
    'timestamp': 1
}

# Loaded keys cache
role_keys_cache = {}


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
  from oll_sc.api import sc_export_pub_key_pem

  pub_key_pem = sc_export_pub_key_pem(key_slot, pin).decode('utf-8')
  return import_rsakey_from_pem(pub_key_pem)


@contextmanager
def load_repository(repo_path):
  """ Load a tuf repository, given a path of an authentication repository.
  This repository is expected to contain a metadata folder, where all tuf metadata files are
  stored. Since TUF expects all metadata files to be in a metadata.staged directory, this function
  creates that directories, copies all metadata files and then deletes it.

  Args:
    - repo_path(str): Path of an authentication repository.

  Returns:
    Repository that comforms to `taf.repository_tool.Repository`

  Raises:
    - OSError: If `metadata.staged` cannot be created
    - securesystemslib.exceptions.FormatError: If 'repository_directory' or any of the metadata
                                               files are improperly formatted.

    - securesystemslib.exceptions.RepositoryError: If the Root role cannot be found.
                                                    At a minimum, a repository must contain
                                                    'root.json'
  """
  from tuf.repository_tool import load_repository as load_tuf_repository

  # create a metadata.staged directory and copy all
  # files from the metadata directory
  staged_dir = os.path.join(repo_path, METADATA_STAGED_DIRECTORY_NAME)
  metadata_dir = os.path.join(repo_path, METADATA_DIRECTORY_NAME)

  shutil.copytree(metadata_dir, staged_dir)

  tuf_repository = load_tuf_repository(repo_path)
  repository = Repository(tuf_repository, repo_path)
  yield repository

  # copy everything from the staged directory to the metadata directory
  # and removed metadata.staged
  for filename in os.listdir(staged_dir):
    shutil.copy(os.path.join(staged_dir, filename), metadata_dir)
  shutil.rmtree(staged_dir)


def load_role_key(keystore, role, password=None):
  """Loads the specified role's key from a keystore file.
  The keystore file can, but doesn't have to be password protected.

  NOTE: Keys inside keystore should match a role name!

  Args:
    - keystore(str): Path to the keystore directory
    - role(str): TUF role (root, targets, timestamp, snapshot or delegated one)
    - password(str): (Optional) password used for PEM decryption

  Returns:
    - An RSA key object, conformant to 'securesystemslib.RSAKEY_SCHEMA'.

  Raises:
    - securesystemslib.exceptions.FormatError: If the arguments are improperly formatted.
    - securesystemslib.exceptions.CryptoError: If path is not a valid encrypted key file.
  """
  key = role_keys_cache.get(role, None)
  if key is None:
    from tuf.repository_tool import import_rsa_privatekey_from_file

    key = import_rsa_privatekey_from_file(os.path.join(keystore, role), password=password)
    role_keys_cache[role] = key
  return key


def targets_signature_provider(key_id, key_slot, key_pin, data):
  """Targets signature provider used to sign data with YubiKey.

  Args:
    - key_id(str): Key id from targets metadata file
    - key_slot(tuple): Key slot on smart card (YubiKey)
    - key_pin(str): PIN for signing key
    - data(dict): Data to sign

  Returns:
    Dictionary that comforms to `securesystemslib.formats.SIGNATURE_SCHEMA`

  Raises:
    - SmartCardError: If signing with YubiKey cannot be performed
  """
  from binascii import hexlify
  from oll_sc.api import sc_sign_rsa_pkcs_pss_sha256

  data = securesystemslib.formats.encode_canonical(data)
  signature = sc_sign_rsa_pkcs_pss_sha256(data, key_slot, key_pin)

  return {
      'keyid': key_id,
      'sig': hexlify(signature).decode()
  }


class Repository:

  def __init__(self, repository, repository_path):
    self._repository = repository
    self.repository_path = repository_path

  _required_files = ['repositories.json']

  @property
  def targets_path(self):
    return os.path.join(self.repository_path, TARGETS_DIRECTORY_NAME)

  @property
  def metadata_path(self):
    return os.path.join(self.repository_path, METADATA_DIRECTORY_NAME)

  @property
  def metadata_staged_path(self):
    return os.path.join(self.repository_path, METADATA_STAGED_DIRECTORY_NAME)

  def _add_target(self, targets_obj, file_path, custom=None):
    normalize_file_line_endings(
        os.path.join(self.repository_path, TARGETS_DIRECTORY_NAME, file_path))
    targets_obj.add_target(file_path, custom)

  def _role_obj(self, role):
    """Helper function for getting TUF's role object, given the role's name

    Args:
      - role(str): TUF role (root, targets, timestamp, snapshot or delegated one)

    Returns:
      One of metadata objects:
        Root, Snapshot, Timestamp, Targets or delegated metadata

    Raises:
      - securesystemslib.exceptions.FormatError: If the arguments are improperly formatted.
      - securesystemslib.exceptions.UnknownRoleError: If 'rolename' has not been delegated by this
                                                      targets object.
   """
    if role == 'targets':
      return self._repository.targets
    elif role == 'snapshot':
      return self._repository.snapshot
    elif role == 'timestamp':
      return self._repository.timestamp
    elif role == 'root':
      return self._repository.root
    return self._repository.targets(role)

  def _try_load_metadata_key(self, role, key):
    """Check if given key can be used to sign given role and load it.

    Args:
      - role(str): TUF role (root, targets, timestamp, snapshot or delegated one)
      - key(securesystemslib.formats.RSAKEY_SCHEMA): Private key used to sign metadata

    Returns:
      None

    Raises:
      - securesystemslib.exceptions.FormatError: If the arguments are improperly formatted.
      - securesystemslib.exceptions.UnknownRoleError: If 'rolename' has not been delegated by this
                                                      targets object.
      - InvalidKeyError: If metadata cannot be signed with given key.
    """
    if not self.is_valid_metadata_key(role, key):
      raise InvalidKeyError(role)
    self._role_obj(role).load_signing_key(key)

  def _update_metadata(self, role, start_date=datetime.datetime.now(), interval=None, write=False):
    """Update metadata expiration date and (optionally) writes it.

    Args:
      - role(str): TUF role (root, targets, timestamp, snapshot or delegated one)
      - start_date(datetime): Date to which the specified interval is added when
                              calculating expiration date. If a value is not
                              provided, it is set to the current time
      - interval(int): Number of days added to the start date. If not provided,
                      the default value is used
      - write(bool): If True metadata will be signed and written

    Returns:
      - None

    Raises:
      - securesystemslib.exceptions.Error: If securesystemslib error happened during metadata write
      - tuf.exceptions.Error: If TUF error happened during metadata write
    """
    self.set_metadata_expiration_date(role, start_date, interval)
    if write:
      self._repository.write(role)

  def add_existing_target(self, file_path, targets_role='targets', custom=None):
    """Registers new target files with TUF.
    The files are expected to be inside the targets directory.

    Args:
      - file_path(str): Path to target file
      - targets_role(str): Targets or delegated role: a targets role (the root targets role
                           or one of the delegated ones)
      - custom(dict): Custom information for given file

    Returns:
      None

    Raises:
      - securesystemslib.exceptions.FormatError: If 'filepath' is improperly formatted.
      - securesystemslib.exceptions.Error: If 'filepath' is not located in the repository's targets
                                           directory.
    """
    targets_obj = self._role_obj(targets_role)
    self._add_target(targets_obj, file_path, custom)

  def add_targets(self, data, targets_role='targets', files_to_keep=None):
    """Creates a target .json file containing a repository's commit for each repository.
    Adds those files to the tuf repository. Also removes all targets from the filesystem if their
    path is not among the provided ones. TUF does not delete targets automatically.

    Args:
      - data(dict): Dictionary whose keys are target paths of repositories
                    (as specified in targets.json, relative to the targets dictionary).
                    The values are of form:
                    {
                      target: content of the target file
                      custom: {
                        custom_field1: custom_value1,
                        custom_field2: custom_value2
                      }
                    }

      Content of the target file can be a dictionary, in which case a jason file will be created.
      If that is not the case, an ordinary textual file will be created.
      If target is not specified and the file already exists, it will not be modified.
      If it does not exist, an empty file will be created. To replace an existing file with an
      empty file, specify empty content (target: '')

      Custom is an optional property which, if present, will be used to specify a TUF target's

      - targets_role(str): Targets or delegated role: a targets role (the root targets role
                           or one of the delegated ones)
      - files_to_keep(list|tuple): List of files defined in the previous version of targets.json
                                   that should remain targets. Files required by the framework will
                                   also remain targets.
    """
    if files_to_keep is None:
      files_to_keep = []
    # leave all files required by the framework and additional files specified by the user
    files_to_keep.extend(self._required_files)

    # delete files if they no longer correspond to a target defined
    # in targets metadata and are not specified in files_to_keep
    for root, _, files in os.walk(self.targets_path):
      for filename in files:
        filepath = os.path.join(root, filename)
        if filepath not in data and filename not in files_to_keep:
          os.remove(filepath)

    targets_obj = self._role_obj(targets_role)

    for path, target_data in data.items():
      # if the target's parent directory should not be "targets", create
      # its parent directories if they do not exist
      target_path = os.path.join(self.targets_path, path)
      if not os.path.exists(os.path.dirname(target_path)):
        os.makedirs(os.path.dirname(target_path))

      # create the target file
      content = target_data.get('target', None)
      if content is None:
        if not os.path.isfile(target_path):
          Path(target_path).touch()
      else:
        with open(target_path, 'w') as f:
          if isinstance(content, dict):
            json.dump(content, f, indent=4)
          else:
            f.write(content)

      custom = target_data.get('custom', None)
      self._add_target(targets_obj, target_path, custom)

    with open(os.path.join(self.metadata_path, '{}.json'.format(targets_role))) as f:
      previous_targets = json.load(f)['signed']['targets']

    for path in files_to_keep:
      # if path if both in data and files_to_keep, skip it
      # e.g. repositories.json will always be in files_to_keep,
      # but it might also be specified in data, if it needs to be updated
      if path in data:
        continue
      target_path = os.path.join(self.targets_path, path)
      previous_custom = previous_targets[path].get('custom')
      self._add_target(targets_obj, target_path, previous_custom)

  def get_role_keys(self, role):
    """Registers new target files with TUF.
    The files are expected to be inside the targets directory.

    Args:
      - role(str): TUF role (root, targets, timestamp, snapshot or delegated one)

    Returns:
      List of the role's keyids (i.e., keyids of the keys).

    Raises:
      - securesystemslib.exceptions.FormatError: If the arguments are improperly formatted.
      - securesystemslib.exceptions.UnknownRoleError: If 'rolename' has not been delegated by this
                                                      targets object.
    """
    role_obj = self._role_obj(role)
    return role_obj.keys

  def is_valid_metadata_key(self, role, key):
    """Checks if metadata role contains key id of provided key.

    Args:
      - role(str): TUF role (root, targets, timestamp, snapshot or delegated one)
      - key(securesystemslib.formats.RSAKEY_SCHEMA): Timestamp key.

    Returns:
      Boolean. True if key id is in metadata role key ids, False otherwise.

    Raises:
      - securesystemslib.exceptions.FormatError: If key does not match RSAKEY_SCHEMA
      - securesystemslib.exceptions.UnknownRoleError: If role does not exist
    """
    securesystemslib.formats.RSAKEY_SCHEMA.check_match(key)

    return key['keyid'] in self.get_role_keys(role)

  def is_valid_metadata_yubikey(self, role, key_slot, pin):
    """Checks if metadata role contains key id from YubiKey.

    Args:
      - role(str): TUF role (root, targets, timestamp, snapshot or delegated one)
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
    return self.is_valid_metadata_key(role, public_key)

  def set_metadata_expiration_date(self, role, start_date=datetime.datetime.now(), interval=None):
    """Set expiration date of the provided role.

    Args:
      - role(str): TUF role (root, targets, timestamp, snapshot or delegated one)
      - start_date(datetime): Date to which the specified interval is added when calculating
                            expiration date. If a value is not provided, it is set to the
                            current time.
      - interval(int): A number of days added to the start date.
                       If not provided, the default value is set based on the role:

                        root - 365 days
                        targets - 90 days
                        snapshot - 7 days
                        timestamp - 1 day
                        all other roles - 1 day

    Returns:
      None

    Raises:
      - securesystemslib.exceptions.FormatError: If the arguments are improperly formatted.
      - securesystemslib.exceptions.UnknownRoleError: If 'rolename' has not been delegated by this
                                                      targets object.
    """
    role_obj = self._role_obj(role)
    if interval is None:
      interval = expiration_intervals.get(role, 1)
    expiration_date = start_date + datetime.timedelta(interval)
    role_obj.expiration = expiration_date

  def update_snapshot(self, snapshot_key, start_date=datetime.datetime.now(), interval=None, write=True):
    """Update snapshot metadata.

    Args:
      - snapshot_key(securesystemslib.formats.RSAKEY_SCHEMA): Snapshot key.
      - start_date(datetime): Date to which the specified interval is added when
                              calculating expiration date. If a value is not
                              provided, it is set to the current time
      - interval(int): Number of days added to the start date. If not provided,
                      the default value is used
      - write(bool): If True snapshot metadata will be signed and written

    Returns:
      None

    Raises:
      - InvalidKeyError: If wrong key is used to sign metadata
      - SnapshotMetadataUpdateError: If any other error happened during metadata update
    """
    try:
      self._try_load_metadata_key('snapshot', snapshot_key)
      self._update_metadata('snapshot', start_date, interval, write=write)
    except (TUFError, SSLibError) as e:
      raise SnapshotMetadataUpdateError(str(e))

  def update_snapshot_and_timestmap(self, keystore, write=True, **kwargs):
    """Update snapshot and timestamp metadata.

    Args:
      - keystore(str): Path to the keystore directory
      - write(bool): (Optional) If True snapshot and timestamp metadata will be signed and written
      - kwargs(dict): (Optional) Expiration dates and intervals:
                      - snapshot_date(datetime)
                      - snapshot_interval(int)
                      - timestamp_date(datetime)
                      - timestamp_ionterval(int)

    Returns:
      None

    Raises:
      - InvalidKeyError: If wrong key is used to sign metadata
      - MetadataUpdateError: If any other error happened during metadata update
    """
    try:
      snapshot_date = kwargs.get('snapshot_date', datetime.datetime.now())
      snapshot_interval = kwargs.get('snapshot_interval', None)

      timestamp_date = kwargs.get('timestamp_date', datetime.datetime.now())
      timestamp_interval = kwargs.get('timestamp_interval', None)

      snapshot_key = load_role_key(keystore, 'snapshot')
      timestamp_key = load_role_key(keystore, 'timestamp')

      self.update_snapshot(snapshot_key, snapshot_date, snapshot_interval, write=write)
      self.update_timestamp(timestamp_key, timestamp_date, timestamp_interval, write=write)

    except (TUFError, SSLibError) as e:
      raise MetadataUpdateError('all', str(e))

  def update_targets(self, targets_key_slot, targets_key_pin, targets_data=None,
                     start_date=datetime.datetime.now(), interval=None, write=True):
    """Update target data, sign with smart card and write.

    Args:
      - targets_key_slot(tuple|int): Slot with key on a smart card used for signing
      - targets_key_pin(str): Targets key pin
      - targets_data(dict): (Optional) Dictionary with targets data
      - start_date(datetime): Date to which the specified interval is added when
                              calculating expiration date. If a value is not
                              provided, it is set to the current time
      - interval(int): Number of days added to the start date. If not provided,
                       the default value is used
      - write(bool): If True targets metadata will be signed and written

    Returns:
      None

    Raises:
      - InvalidKeyError: If wrong key is used to sign metadata
      - MetadataUpdateError: If any other error happened during metadata update
    """
    if isinstance(targets_key_slot, int):
      targets_key_slot = (targets_key_slot, )

    try:
      if not self.is_valid_metadata_yubikey('targets', targets_key_slot, targets_key_pin):
        raise InvalidKeyError('targets')

      pub_key = get_yubikey_public_key(targets_key_slot, targets_key_pin)

      if targets_data:
        self.add_targets(targets_data)

      self.set_metadata_expiration_date('targets', start_date, interval)

      self._repository.targets.add_external_signature_provider(
          pub_key,
          partial(targets_signature_provider, pub_key['keyid'], targets_key_slot, targets_key_pin)
      )
      if write:
        self._repository.write('targets')

    except (SmartCardError, TUFError, SSLibError) as e:
      raise TargetsMetadataUpdateError(str(e))

  def update_timestamp(self, timestamp_key, start_date=datetime.datetime.now(), interval=None, write=True):
    """Update timestamp metadata.

    Args:
      - timestamp_key(securesystemslib.formats.RSAKEY_SCHEMA): Timestamp key.
      - start_date(datetime): Date to which the specified interval is added when
                              calculating expiration date. If a value is not
                              provided, it is set to the current time
      - interval(int): Number of days added to the start date. If not provided,
                      the default value is used
      - write(bool): If True timestmap metadata will be signed and written

    Returns:
      None

    Raises:
      - InvalidKeyError: If wrong key is used to sign metadata
      - TimestampMetadataUpdateError: If any other error happened during metadata update
    """
    try:
      self._try_load_metadata_key('timestamp', timestamp_key)
      self._update_metadata('timestamp', start_date, interval, write=write)
    except (TUFError, SSLibError) as e:
      raise TimestampMetadataUpdateError(str(e))

  def writeall(self):
    """Write all dirty metadata files.

    Args:
      None

    Returns:
      None

    Raises:
      - tuf.exceptions.UnsignedMetadataError: If any of the top-level and delegated roles do not
                                              have the minimum threshold of signatures.
    """
    self._repository.writeall()
