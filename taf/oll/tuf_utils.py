import getpass
import json
import os
import shutil
from contextlib import contextmanager
from pathlib import Path
import securesystemslib

role_keys_cache = {}

class TUFRepository:

  def __init__(self, repository, repository_path):
    self.repository = repository
    self.repository_path = repository_path

  @property
  def targets_path(self):
    return os.path.join(self.repository_path, 'targets')

  @property
  def metadata_path(self):
    return os.path.join(self.repository_path, 'metadata')

  @property
  def metadata_staged_path(self):
    return os.path.join(self.repository_path, 'metadata.staged')

  def add_existing_target(self, file_path, targets_role='targets'):
    """
    Registers new target files with TUF. The files are expected to be
    inside the targets directory.
    """
    targets = self._role_obj(targets_role)
    targets.add_target(os.path.join(self.targets_path, file_path))


  def add_targets(self, data, targets_role='targets', files_to_keep=['repositories.json']):
    """
    Creates a target .json file containing a repository's commit for each
    repository. Adds those files to the tuf repostiory. Aslo removes
    all targets from the filesystem if the their path is not among the
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
      If that is not the case, an oridinary textual file will be created.
      If target is not specified and the file already exists, it will not be modified. If it does not exist,
      an empty file will be created. To replace an existing  file with an empty file, specify empty
      content (target: '')

      Custom is an optional property which, if present, will be used to specify a TUF target's
      custom data. This is supported by TUF and is directly written to the metadata file.

      targets_role: a targets role (the root targets role, or one of the delegated ones)
      files_to_keep: a list of files defined in the previous version of targets.json that should remain
        targets.
    """
    # delete files if they no longer correspond to a target defined
    # in targets metadata
    for root, dirs, files in os.walk(self.targets_path):
      for filename in files:
        filepath = os.path.join(root, filename)
        if filepath not in data and filename not in files_to_keep:
          os.remove(filepath)

    targets = self._role_obj(targets_role)
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
      targets.add_target(target_path, custom)

    with open(os.path.join(self.metadata_path, f'{targets_role}.json')) as f:
      previous_targets = json.load(f)['signed']['targets']

    for path in files_to_keep:
      target_path = os.path.join(self.targets_path, path)
      previous_custom = previous_targets[path].get('custom')
      targets.add_target(target_path, previous_custom)


  def _role_obj(self, role):
    """
    A helper function which returns tuf's role object, given the role's name
    args:
      repository: a tuf repository
      role: a role (either one of tuf's root roles, or a delegated target name
   """
    if role == 'targets':
      return self.repository.targets
    elif role == 'snapshot':
      return self.repository.snapshot
    elif role == 'timestamp':
      return self.repository.timestamp
    elif role == 'root':
      return self.repository.root
    return self.repository.targets(role)


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
      self.repository.write(role)
    else:
      snapshot_key = load_role_key('snapshot', keystore)
      self.repository.snapshot.load_signing_key(snapshot_key)
      timestamp_key = load_role_key('timestamp', keystore)
      self.repository.timestamp.load_signing_key(timestamp_key)
      self.repository.writeall()


def load_role_key(role, keystore):
  """
  Loads the speicified role's key from a keystore file.
  The keystore file can, but doesn't have to be password
  protected. If it is, a user is prompted to enter the passphrase.
  Args:
    role: TUF role (root, targets, timestamp, shapshot)
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
  from tuf.repository_tool import load_repository

  # create a metadata.staged directory and copy all
  # files from the metadata directory
  staged_dir = os.path.join(repo_path, 'metadata.staged')
  metadata_dir = os.path.join(repo_path, 'metadata')
  os.mkdir(staged_dir)
  for filename in os.listdir(metadata_dir):
    shutil.copy(os.path.join(metadata_dir, filename), staged_dir)

  repository = load_repository(repo_path)
  tuf_repository = TUFRepository(repository, repo_path)
  yield tuf_repository

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
