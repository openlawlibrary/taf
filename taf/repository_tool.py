import getpass
import datetime
import json
import os
import shutil
from contextlib import contextmanager
from pathlib import Path
from taf.utils import normalize_file_line_endings

import securesystemslib

role_keys_cache = {}


expiration_intervals = {
  'root': 365,
  'targets': 90,
  'snapshot': 7,
  'timestamp': 1
}


class Repository:

  def __init__(self, repository, repository_path):
    self._repository = repository
    self.repository_path = repository_path

  _required_files = ['repositories.json']

  @property
  def targets_path(self):
    return os.path.join(self.repository_path, 'targets')

  @property
  def metadata_path(self):
    return os.path.join(self.repository_path, 'metadata')

  @property
  def metadata_staged_path(self):
    return os.path.join(self.repository_path, 'metadata.staged')

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
    for root, dirs, files in os.walk(self.targets_path):
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

    with open(os.path.join(self.metadata_path, f'{targets_role}.json')) as f:
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
      all other roels - 1 day
    """
    role_obj = self._role_obj(role)
    if interval is None:
      interval = expiration_intervals.get(role, 1)
    expiration_date = start_date + datetime.timedelta(interval)
    role_obj.expiration = expiration_date

  def write_roles_metadata(self, role, keystore, update_snapshot_and_timestamp=False):
    """
    Generates metadata of just one metadata file, corresponding
    to the provided role
    args:
      repository: a tu repository
      role: a tuf role
      keystore: location of the keystore file
      update_snapshot_and_timestamp: should timestamp and snapshot.json also be udpated
    """
    private_role_key = load_role_key(role, keystore)
    self._role_obj(role).load_signing_key(private_role_key)
    # only write this role's metadata

    if not update_snapshot_and_timestamp:
      self._repository.write(role)
    else:
      snapshot_key = load_role_key('snapshot', keystore)
      self._repository.snapshot.load_signing_key(snapshot_key)
      timestamp_key = load_role_key('timestamp', keystore)
      self._repository.timestamp.load_signing_key(timestamp_key)
      self._repository.writeall()


def load_role_key(role, keystore):
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
      # try loading the key without passing in a passphare
      # if that fails, prompt the user to enter it
      key = import_rsa_privatekey_from_file(os.path.join(keystore, role))
    except securesystemslib.exceptions.CryptoError:
      while key is None:
        passphrase = getpass.getpass(f'Enter {role} passphrase:')
        try:
          key = import_rsa_privatekey_from_file(os.path.join(keystore, role), passphrase)
        except:
          pass
    role_keys_cache[role] = key
  return key


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
  staged_dir = os.path.join(repo_path, 'metadata.staged')
  metadata_dir = os.path.join(repo_path, 'metadata')
  os.mkdir(staged_dir)
  for filename in os.listdir(metadata_dir):
    shutil.copy(os.path.join(metadata_dir, filename), staged_dir)

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
