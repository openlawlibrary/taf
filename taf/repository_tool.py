import datetime
import getpass
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
                                 TARGETS_DIRECTORY_NAME)

from .exceptions import (InvalidKeyError, MetadataUpdateError,
                         SnapshotMetadataUpdateError,
                         TargetsMetadataUpdateError,
                         TimestampMetadataUpdateError)

role_keys_cache = {}


expiration_intervals = {
    'root': 365,
    'targets': 90,
    'snapshot': 7,
    'timestamp': 1
}


@contextmanager
def load_repository(repo_path):
  """
  Load a tuf repository, given a path of an authentication
  repository. This repository is expected to contain a metadata
  folder, where all tuf metadata files are stored. Since TUF expects
  all metadata files to be in a metadata.staged directory, this
  function created that directories, copies all metadata files
  and then deletes it.
  Args:
    repo_path: path of an authentication repository.
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


def mark_role_as_dirty(role):
  """
  Mark a tuf role as dirty. This can be used to make tuf
  generate new timestamp and snapshot, if they cannot be
  generated at the same time as targets metadata
  args:
    role: a tuf role
  """
  import tuf
  roleinfo = tuf.roledb.get_roleinfo(role)
  tuf.roledb.update_roleinfo(role, roleinfo)


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

  def add_existing_target(self, file_path, targets_role='targets', custom=None):
    """
    Registers new target files with TUF. The files are expected to be
    inside the targets directory.
    """
    targets_obj = self._role_obj(targets_role)
    self._add_target(targets_obj, file_path, custom)

  def add_targets(self, data, targets_role='targets', files_to_keep=None):
    """
    Creates a target .json file containing a repository's commit for each
    repository. Adds those files to the tuf repository. Also removes
    all targets from the filesystem if their path is not among the
    provided ones. TUF does not delete targets automatically.
    Args:
      data: a dictionary whose keys are target paths of repositories
      (as specified in targets.json, relative to the targets dictionary),
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
      custom data. This is supported by TUF and is directly written to the metadata file.

      targets_role: a targets role (the root targets role, or one of the delegated ones)
      files_to_keep: a list of files defined in the previous version of targets.json that should
      remain targets. Files required by the framework will also remain targets.
    """
    if files_to_keep is None:
      files_to_keep = []
    # leave all files required by the framework and additional files specified
    # by the user
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

  def _add_target(self, targets_obj, file_path, custom=None):
    normalize_file_line_endings(os.path.join(self.repository_path, 'targets', file_path))
    targets_obj.add_target(file_path, custom)

  def _role_obj(self, role):
    """
    A helper function which returns TUF's role object, given the role's name
    args:
      repository: a TUF repository
      role: a role (either one of TUF's root roles, or a delegated target name
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

  def get_role_keys(self, role):
    role_obj = self._role_obj(role)
    return role_obj.keys

  def set_metadata_expiration_date(self, role, start_date=datetime.datetime.now(), interval=None):
    """
    Set expiration date of the provided role.
    Args:
      role: a tuf role
      start_date: a date to which the specified interval is added when calculating expiration date.
      If a value is not provided, it is set to the current time
      interval: a number of days added to the start date. If not provided, the default value is
      set based on the role:
      root - 365 days
      targets - 90 days
      snapshot - 7 days
      timestamp - 1 day
      all other roles - 1 day
    """
    role_obj = self._role_obj(role)
    if interval is None:
      interval = expiration_intervals.get(role, 1)
    expiration_date = start_date + datetime.timedelta(interval)
    role_obj.expiration = expiration_date

  def update_snapshot_and_timestmap(self, keystore, **kwargs):
    """Update snapshot and timestamp metadata.

    Args:
      - keystore(str): Path to keystore with snapshot and timestamp keys
      - kwargs(dict): (Optional) Expiration dates and intervals

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

      self.update_snapshot(snapshot_key, snapshot_date, snapshot_interval, write=False)
      self.update_timestamp(timestamp_key, timestamp_date, timestamp_interval, write=False)

      self._repository.writeall()

    except (TUFError, SSLibError) as e:
      raise MetadataUpdateError('all', str(e))

  def update_snapshot(self, snapshot_key, start_date=datetime.datetime.now(), interval=None, write=True):
    """Update snapshot metadata.

    Args:
      - snapshot_key(securesystemslib.formats.RSAKEY_SCHEMA): Snapshot key.
      - start_date(datetime): Date to which the specified interval is added when
                              calculating expiration date. If a value is not
                              provided, it is set to the current time
      - interval(int): A number of days added to the start date. If not provided,
                      the default value is used
      - write(bool): If True snapshot metadata will be signed and written

    Returns:
      None

    Raises:
      - InvalidKeyError: If wrong key is used to sign metadata
      - SnapshotMetadataUpdateError: If any other error happened during metadata update
    """
    from .sc_utils import is_valid_metadata_key

    try:
      if not is_valid_metadata_key(self, 'snapshot', snapshot_key):
        raise InvalidKeyError('snapshot')

      self.set_metadata_expiration_date('snapshot', start_date, interval)

      self._repository.snapshot.load_signing_key(snapshot_key)
      if write:
        self._repository.write('snapshot')

    except (TUFError, SSLibError) as e:
      raise SnapshotMetadataUpdateError(str(e))

  def update_timestamp(self, timestamp_key, start_date=datetime.datetime.now(), interval=None, write=True):
    """Update timestamp metadata.

    Args:
      - timestamp_key(securesystemslib.formats.RSAKEY_SCHEMA): Timestamp key.
      - start_date(datetime): Date to which the specified interval is added when
                              calculating expiration date. If a value is not
                              provided, it is set to the current time
      - interval(int): A number of days added to the start date. If not provided,
                      the default value is used
      - write(bool): If True timestmap metadata will be signed and written

    Returns:
      None

    Raises:
      - InvalidKeyError: If wrong key is used to sign metadata
      - TimestampMetadataUpdateError: If any other error happened during metadata update
    """
    from .sc_utils import is_valid_metadata_key

    try:
      if not is_valid_metadata_key(self, 'timestamp', timestamp_key):
        raise InvalidKeyError('timestamp')

      self.set_metadata_expiration_date('timestamp', start_date, interval)

      self._repository.timestamp.load_signing_key(timestamp_key)
      if write:
        self._repository.write('timestamp')

    except (TUFError, SSLibError) as e:
      raise TimestampMetadataUpdateError(str(e))

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
      - interval(int): A number of days added to the start date. If not provided,
                       the default value is used
      - write(bool): If True targets metadata will be signed and written

    Returns:
      None

    Raises:
      - InvalidKeyError: If wrong key is used to sign metadata
      - MetadataUpdateError: If any other error happened during metadata update
    """
    from .sc_utils import get_yubikey_public_key, is_valid_metadata_yubikey

    if isinstance(targets_key_slot, int):
      targets_key_slot = (targets_key_slot, )

    try:
      if not is_valid_metadata_yubikey(self, 'targets', targets_key_slot, targets_key_pin):
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


def load_role_key(keystore, role, password=None):
  """
  Loads the specified role's key from a keystore file.
  The keystore file can, but doesn't have to be password
  protected. If it is, a user is prompted to enter the passphrase.
  Args:
    role: TUF role (root, targets, timestamp, snapshot)
    keystore: location of the keystore file
  """
  key = role_keys_cache.get(role, None)
  if key is None:
    from tuf.repository_tool import import_rsa_privatekey_from_file
    try:
      # try loading the key without passing in a passphrase
      # if that fails, prompt the user to enter it
      key = import_rsa_privatekey_from_file(os.path.join(keystore, role), password=password)
    except securesystemslib.exceptions.CryptoError:
      while key is None:
        passphrase = getpass.getpass('Enter {} passphrase:'.format(role))
        try:
          key = import_rsa_privatekey_from_file(
              os.path.join(keystore, role), passphrase)
        except securesystemslib.exceptions.Error:
          pass
    role_keys_cache[role] = key
  return key
