import os
import json
import shutil
from pathlib import Path
from contextlib import contextmanager

role_keys_cache = {}

def add_targets(repository, paths_and_commits, targets_role='targets'):
  """
  Creates a target .json file containing a repository's commit for each
  repository. Adds those files to the tuf repostiory. Aslo removes
  all targets from the filesystem if the their path is not among the
  provided ones. TUF does not delete targets automatically.
  Args:
    repository: TUF repository
    paths_and_commits: a dictionary whose keys are full paths repositories
    (as specified in targets.json, but without the targets directory) and
    whose values are commits which will be stored in target files
    targets_role: a targets role (the root targets role, or one of the delegated ones)
  """
  repository_dir = repository._repository_directory
  targets_dir = os.path.join(repository_dir, 'targets')

  # delete files if they they no longer correspond to a target defined
  # in targets metadata
  for root, dirs, files in os.walk(targets_dir):
    for filename in files:
      filepath = os.pah.join(root, filename)
      # remove the extension
      filepath, _ = os.path.splitext(filepath)
      if not filepath in paths_and_commits:
        os.remove(filepath)

  targets = _targets_role_obj(repository, targets_role)
  for path, commit in paths_and_commits.items():
    target_path = os.path.join(repository_dir, 'targets', path)
    if not os.path.exists(os.path.dirname(target_path)):
      os.makedirs(os.path.dirname(target_path))
    with open(target_path, 'w') as f:
      json.dump({'commit': commit}, f, indent=4)

    targets.add_target(os.path.join(target_path))

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
  roleinfo = tuf.roledb.get_roleinfo(role)
  tuf.roledb.update_roleinfo(role, roleinfo)


def set_capstone(repository, capstone, targets_role='targets'):
  """
  Creates or removes a capstone file, depending on the value of the
  capstone parameter
  Args:
    repository: tuf repository
    capstone: indicator if capstone should be added or removed
    targets_role: a targets role (the root targets role, or one of the delegated ones)
  """
  path = os.path.join(repository._repository_directory, 'targets', 'capstone')

  if capstone:
    Path(path).touch()
    _targets_role_obj(repository, targets_role).add_target('capstone')
  else:
    os.remove(path)


def _targets_role_obj(repository, role):
  """
  A helper function which returns tuf's targets object
  given a role.
  args:
    repository: a tuf repository
    role: a targets role (the root targets role, or one of the delegated ones)
  """
  if role == 'targets':
    return repository.targets
  return repository.targets(role)


def write_roles_metadata(repository, role, keystore):
  """
  Generates metadata of just one metadata file, corresponding
  to the provided role
  args:
    repository: a tu repository
    role: a tuf role
    keystore: location of the keystore file
  """
  private_role_key = load_role_key(role, keystore)
  _targets_role_obj(repository, role).load_signing_key(private_role_key)
  # only write this role's metadata
  repository.write(role)
