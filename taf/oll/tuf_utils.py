import os
import json
import shutil
from pathlib import Path
from contextlib import contextmanager
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

  def add_targets(self, paths_and_commits, targets_role='targets'):
    """
    Creates a target .json file containing a repository's commit for each
    repository. Adds those files to the tuf repostiory. Aslo removes
    all targets from the filesystem if the their path is not among the
    provided ones. TUF does not delete targets automatically.
    Args:
      paths_and_commits: a dictionary whose keys are full paths repositories
      (as specified in targets.json, but without the targets directory) and
      whose values are commits which will be stored in target files
      targets_role: a targets role (the root targets role, or one of the delegated ones)
    """
    # delete files if they they no longer correspond to a target defined
    # in targets metadata
    for root, dirs, files in os.walk(self.targets_path):
      for filename in files:
        filepath = os.path.join(root, filename)
        # remove the extension
        filepath, _ = os.path.splitext(filepath)
        if not filepath in paths_and_commits:
          os.remove(filepath)

    targets = self._role_obj(targets_role)
    for path, commit in paths_and_commits.items():
      target_path = os.path.join(self.targets_path, path)
      if not os.path.exists(os.path.dirname(target_path)):
        os.makedirs(os.path.dirname(target_path))
      with open(target_path, 'w') as f:
        json.dump({'commit': commit}, f, indent=4)

      targets.add_target(target_path)

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

  def set_capstone(self, capstone, targets_role='targets'):
    """
    Creates or removes a capstone file, depending on the value of the
    capstone parameter
    Args:
      repository: tuf repository
      capstone: indicator if capstone should be added or removed
      targets_role: a targets role (the root targets role, or one of the delegated ones)
    """
    path = os.path.join(self.targets_path, 'capstone')

    if capstone:
      Path(path).touch()
      self._role_obj(targets_role).add_target('capstone')
    else:
      if os.path.isfile(path):
        os.remove(path)

  def write_roles_metadata(self, role, keystore):
    """
    Generates metadata of just one metadata file, corresponding
    to the provided role
    args:
      repository: a tu repository
      role: a tuf role
      keystore: location of the keystore file
    """
    private_role_key = load_role_key(role, keystore)
    self._role_obj(role).load_signing_key(private_role_key)
    # only write this role's metadata
    self.repository.write(role)


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
        passphrase = getpass(f'Enter {role} passphrase:')
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
