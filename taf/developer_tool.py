import datetime
import json
import os
import pathlib
from collections import defaultdict

import tuf.repository_tool
from tuf.repository_tool import (METADATA_DIRECTORY_NAME,
                                 TARGETS_DIRECTORY_NAME, create_new_repository,
                                 generate_and_write_rsa_keypair,
                                 import_rsa_privatekey_from_file,
                                 import_rsa_publickey_from_file)

from taf.git import GitRepository
from taf.repository_tool import Repository


def add_target_repos(repo_path, targets_directory, namespace=''):
  """
  <Purpose>
    Create or update target files by reading the latest commits of the provided target repositories
  <Arguments>
    repo_path:
      Authentication repository's location
    targets_directory:
      Directory which contains target repositories
    namespace:
      Namespace used to form the full name of the target repositories. E.g. some_namespace/law-xml
  """
  auth_repo_targets_dir = os.path.join(repo_path, TARGETS_DIRECTORY_NAME)
  if namespace:
    auth_repo_targets_dir = os.path.join(auth_repo_targets_dir, namespace)
    if not os.path.exists(auth_repo_targets_dir):
      os.makedirs(auth_repo_targets_dir)
  for target_repo_dir in os.listdir(targets_directory):
    target_repo = GitRepository(os.path.join(targets_directory, target_repo_dir))
    commit = target_repo.head_commit_sha()
    target_repo_name = os.path.basename(target_repo_dir)
    with open(os.path.join(auth_repo_targets_dir, target_repo_name), 'w') as f:
      json.dump({'commit': commit}, f,  indent=4)


def build_auth_repo(repo_path, targets_directory, namespace, targets_relative_dir, keystore,
                    roles_key_infos):
  create_repository(repo_path, keystore, roles_key_infos)
  generate_repositories_json(repo_path, targets_directory, namespace,
                             targets_relative_dir)
  register_target_files(repo_path, keystore, roles_key_infos, commit_msg='Added repositories.json')
  auth_repo_targets_dir = os.path.join(repo_path, TARGETS_DIRECTORY_NAME)
  if namespace:
    auth_repo_targets_dir = os.path.join(auth_repo_targets_dir, namespace)
    if not os.path.exists(auth_repo_targets_dir):
      os.makedirs(auth_repo_targets_dir)
  # group commits by dates
  # first add first repos at a date, then second repost at that date
  commits_by_date = defaultdict(dict)
  target_repositories = []
  for target_repo_dir in os.listdir(targets_directory):
    target_repo = GitRepository(os.path.join(targets_directory, target_repo_dir))
    target_repo_name = os.path.basename(target_repo_dir)
    target_repositories.append(target_repo_name)
    commits = target_repo.list_commits(format='format:%H|%cd', date='short')
    for commit in commits[::-1]:
      sha, date = commit.split('|')
      commits_by_date[date].setdefault(target_repo_name, []).append(sha)

  for date in sorted(commits_by_date.keys()):
    repos_and_commits = commits_by_date[date]
    for target_repo_name in target_repositories:
      if target_repo_name in repos_and_commits:
        for sha in commits_by_date[date][target_repo_name]:
          with open(os.path.join(auth_repo_targets_dir, target_repo_name), 'w') as f:
            json.dump({'commit': sha}, f,  indent=4)
          register_target_files(repo_path, keystore, roles_key_infos,
                                commit_msg='Updated {}'.format(target_repo_name))


def create_repository(repo_path, keystore, roles_key_infos, should_commit=True):
  """
  <Purpose>
    Create a new authentication repository. Generate initial metadata files.
    The initial targets metadata file is empty (does not specify any targets)
  <Arguments>
    repo_path:
      Authentication repository's location
    targets_directory:
      Directory which contains target repositories
    keystore:
      Location of the keystore files
    roles_key_infos:
      A dictionary whose keys are role names, while values contain information about the keys.
    should_commit:
      Indicates if if a the git repository should be initialized, and if the initial metadata
      should be committed
  """
  if os.path.isdir(repo_path):
    print('{} already exists'.format(repo_path))
    return
  tuf.repository_tool.METADATA_STAGED_DIRECTORY_NAME = METADATA_DIRECTORY_NAME
  repository = create_new_repository(repo_path)
  for role_name, key_info in roles_key_infos.items():
    num_of_keys = key_info.get('number', 1)
    passwords = key_info.get('passwords', [None] * num_of_keys)
    threshold = key_info.get('threshold', 1)
    role_obj = _role_obj(role_name, repository)
    role_obj.threshold = threshold
    for key_num in range(num_of_keys):
      key_name = _get_key_name(role_name, key_num, num_of_keys)
      public_key = import_rsa_publickey_from_file(os.path.join(keystore,
                                                               key_name + '.pub'))
      password = passwords[key_num]
      if password:
        private_key = import_rsa_privatekey_from_file(os.path.join(keystore, key_name),
                                                      password)
      else:
        private_key = import_rsa_privatekey_from_file(os.path.join(keystore, key_name))
      role_obj.add_verification_key(public_key)
      role_obj.load_signing_key(private_key)
  repository.writeall()
  if should_commit:
    auth_repo = GitRepository(repo_path)
    auth_repo.init_repo()
    auth_repo.commit('Initial metadata')


def generate_keys(keystore, roles_key_infos):
  """
  <Purpose>
    Generate public and private keys and writes them to disk. Names of keys correspond to names
    of the TUF roles. If more than one key should be generated per role, a counter is appended
    to the role's name. E.g. root1, root2, root3 etc.
  <Arguments>
    keystore:
      Location where the generated files should be saved
    roles_key_infos:
      A dictionary whose keys are role names, while values contain information about the keys.
      This includes:
        - passwords of the keystore files
        - number of keys per role (optional, defaults to one if not provided)
        - key length (optional, defaults to TUF's default value, which is 3072)
      Names of the keys are set to names of the roles plus a counter, if more than one key
      should be generated.
  """
  for role_name, key_info in roles_key_infos.items():
    num_of_keys = key_info.get('number', 1)
    bits = key_info.get('length', 3072)
    passwords = key_info.get('passwords', [''] * num_of_keys)
    for key_num in range(num_of_keys):
      key_name = _get_key_name(role_name, key_num, num_of_keys)
      password = passwords[key_num]
      generate_and_write_rsa_keypair(os.path.join(keystore, key_name), bits=bits,
                                     password=password)


def generate_repositories_json(repo_path, targets_directory, namespace='',
                               targets_relative_dir=None):
  """
  <Purpose>
    Generatesinitial repositories.json
  <Arguments>
    repo_path:
      Authentication repository's location
    targets_directory:
      Directory which contains target repositories
    namespace:
      Namespace used to form the full name of the target repositories. E.g. some_namespace/law-xml
    targets_relative_dir:
      Directory relative to which urls of the target repositories are set, if they do not have remote set
  """
  repositories = {}
  auth_repo_targets_dir = os.path.join(repo_path, TARGETS_DIRECTORY_NAME)
  for target_repo_dir in os.listdir(targets_directory):
    target_repo = GitRepository(os.path.join(targets_directory, target_repo_dir))
    target_repo_name = os.path.basename(target_repo_dir)
    target_repo_namespaced_name = target_repo_name if not namespace else '{}/{}'.format(
        namespace, target_repo_name)
    # determine url to specify in initial repositories.json
    # if the repository has a remote set, use that url
    # otherwise, set url to the repository's absolute or relative path (relative
    # to targets_relative_dir if it is specified)
    url = target_repo.get_remote_url()
    if url is None:
      if targets_relative_dir is not None:
        url = os.path.relpath(target_repo.repo_path, targets_relative_dir)
      else:
        url = target_repo.repo_path
      # convert to posix path
      url = pathlib.Path(url).as_posix()
    repositories[target_repo_namespaced_name] = {'urls': [url]}

  with open(os.path.join(auth_repo_targets_dir, 'repositories.json'), 'w') as f:
    json.dump({'repositories': repositories}, f,  indent=4)


def _get_key_name(role_name, key_num, num_of_keys):
  if num_of_keys == 1:
    return role_name
  else:
    return role_name + str(key_num + 1)


def init_repo(repo_path, targets_directory, namespace, targets_relative_dir,
              keystore, roles_key_infos, targets_key_slot=None, targets_key_pin=None,
              should_commit=True):
  """
  <Purpose>
    Generate initial repository:
    1. Crete tuf authentication repository
    2. Commit initial metadata files if commit == True
    3. Add target repositories
    4. Generate repositories.json
    5. Update tuf metadata
    6. Commit the changes if commit == True
  <Arguments>
    repo_path:
      Authentication repository's location
    targets_directory:
      Directory which contains target repositories
    namespace:
      Namespace used to form the full name of the target repositories. E.g. some_namespace/law-xml
    targets_relative_dir:
      Directory relative to which urls of the target repositories are set, if they do not have remote set
    keystore:
      Location of the keystore files
    roles_key_infos:
      A dictionary whose keys are role names, while values contain information about the keys.
    targets_key_slot(tuple|int):
      Slot with key on a smart card used for signing
    targets_key_pin(str):
      Targets key pin
    should_commit:
      Indicates if if a the git repository should be initialized, and if the initial metadata
      should be committed
  """
  create_repository(repo_path, keystore, roles_key_infos, should_commit)
  add_target_repos(repo_path, targets_directory, namespace)
  generate_repositories_json(repo_path, targets_directory, namespace,
                             targets_relative_dir)
  commit_msg = 'Added initial targets' if should_commit else None
  register_target_files(repo_path, keystore, roles_key_infos, targets_key_slot,
                        targets_key_pin, commit_msg=commit_msg)


def _load_role_key_from_keys_dict(role, roles_key_infos):
  password = None
  if roles_key_infos is not None and len(roles_key_infos):
    if role in roles_key_infos:
      password = roles_key_infos[role].get('passwords', [None])[0] or None
  return password


def register_target_file(repo_path, file_path, keystore, roles_key_infos,
                         targets_key_slot=None, targets_key_pin=None, update_all=True):
  taf_repo = Repository(repo_path)
  taf_repo.add_existing_target(file_path)

  _write_targets_metadata(taf_repo, update_all, keystore, roles_key_infos,
                          targets_key_slot, targets_key_pin)


def register_target_files(repo_path, keystore, roles_key_infos, targets_key_slot=None,
                          targets_key_pin=None, update_all=True, commit_msg=None):
  """
  <Purpose>
    Register all files found in the target directory as targets - updates the targets
    metadata file. Update snapshot and timestamp if update_fall==True. Sign targets
    with yubikey if targets_key_pin and targets_key_slot are provided.
  <Arguments>
    repo_path:
      Authentication repository's path
    keystore:
      Location of the keystore files
    roles_key_infos:
      A dictionary whose keys are role names, while values contain information about the keys.
    targets_key_slot(tuple|int):
      Slot with key on a smart card used for signing
    targets_key_pin(str):
      Targets key pin
    update_all:
      Indicates if snapshot and timestamp should also be updated. Set to True by default
    commit_msg:
      Commit message. If specified, the changes made to the authentication are committed.
  """
  targets_path = os.path.join(repo_path, TARGETS_DIRECTORY_NAME)
  taf_repo = Repository(repo_path)
  for root, _, filenames in os.walk(targets_path):
    for filename in filenames:
      relpath = os.path.relpath(os.path.join(root, filename), targets_path)
      relpath = os.path.normpath(relpath).replace(os.path.sep, '/')
      taf_repo.add_existing_target(relpath)
  _write_targets_metadata(taf_repo, update_all, keystore, roles_key_infos,
                          targets_key_slot, targets_key_pin)
  if commit_msg is not None:
    auth_repo = GitRepository(repo_path)
    auth_repo.commit(commit_msg)


def _role_obj(role, repository):
  if role == 'targets':
    return repository.targets
  elif role == 'snapshot':
    return repository.snapshot
  elif role == 'timestamp':
    return repository.timestamp
  elif role == 'root':
    return repository.root


def update_metadata_expiration_date(repo_path, keystore, roles_key_infos, role,
                                    start_date=datetime.datetime.now(), interval=None, commit_msg=None):
  taf_repo = Repository(repo_path)
  update_methods = {'timestamp': taf_repo.update_timestamp,
                    'snapshot': taf_repo.update_snapshot,
                    'targets': taf_repo.update_targets_from_keystore}
  password = _load_role_key_from_keys_dict(role, roles_key_infos)
  update_methods[role](keystore, password, start_date, interval)

  if commit_msg is not None:
    auth_repo = GitRepository(repo_path)
    auth_repo.commit(commit_msg)


def _write_targets_metadata(taf_repo, update_snapshot_and_timestmap, keystore,
                            roles_key_infos, targets_key_slot=None, targets_key_pin=None):

  if targets_key_slot is not None and targets_key_pin is not None:
    taf_repo.update_targets(targets_key_slot, targets_key_pin)
  else:
    targets_password = _load_role_key_from_keys_dict('targets', roles_key_infos)
    taf_repo.update_targets_from_keystore(keystore, targets_password)

  if update_snapshot_and_timestmap:
    snapshot_password = _load_role_key_from_keys_dict('snapshot', roles_key_infos)
    timestamp_password = _load_role_key_from_keys_dict('timestamp', roles_key_infos)
    taf_repo.update_snapshot_and_timestmap(keystore, snapshot_password=snapshot_password,
                                           timestamp_password=timestamp_password)


# TODO Implement update of repositories.json (updating urls, custom data, adding new repository, removing
# repository etc.)
# TODO create tests for this
