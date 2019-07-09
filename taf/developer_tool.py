import datetime
import json
import os
import pathlib
import securesystemslib
from collections import defaultdict
from binascii import hexlify
import tuf.repository_tool
from tuf.repository_tool import (METADATA_DIRECTORY_NAME,
                                 TARGETS_DIRECTORY_NAME, create_new_repository,
                                 generate_and_write_rsa_keypair,
                                 import_rsa_privatekey_from_file,
                                 import_rsa_publickey_from_file,
                                 import_rsakey_from_pem,
                                 generate_rsa_key)
from tuf.keydb import get_key
from taf.git import GitRepository
from taf.auth_repo import AuthenticationRepo
from taf.repository_tool import Repository, get_yubikey_public_key, load_role_key
from oll_sc.yk_api import yk_serial_num, yk_setup
from oll_sc.api import sc_sign_rsa_pkcs_pss_sha256, sc_export_x509_pem
from getpass import getpass
from functools import partial
from securesystemslib.exceptions import UnknownKeyError
from pathlib import Path


EXPIRATION_INTERVAL = 36500
YUBIKEY_EXPIRATION_DATE = datetime.datetime.now() + datetime.timedelta(days=EXPIRATION_INTERVAL)

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
    repo_path = os.path.join(targets_directory, target_repo_dir)
    if os.path.isdir(repo_path):
      target_repo = GitRepository(os.path.join(targets_directory, target_repo_dir))
      if target_repo.is_git_repository:
        commit = target_repo.head_commit_sha()
        target_repo_name = os.path.basename(target_repo_dir)
        with open(os.path.join(auth_repo_targets_dir, target_repo_name), 'w') as f:
          json.dump({'commit': commit}, f,  indent=4)


def build_auth_repo(repo_path, targets_directory, namespace, targets_relative_dir, keystore,
                    roles_key_infos, repos_custom):
  # read the key infos here, no need to read the file multiple times
  roles_key_infos = _read_input_dict(roles_key_infos)
  create_repository(repo_path, keystore, roles_key_infos)
  generate_repositories_json(repo_path, targets_directory, namespace,
                             targets_relative_dir, repos_custom)
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
    target_repo.checkout_branch('master')
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


def create_repository(repo_path, keystore, roles_key_infos, commit_message=None):
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
    commit_message:
      If provided, the changes will be committed automatically using the specified message
  """
  yubikeys = defaultdict(dict)
  roles_key_infos = _read_input_dict(roles_key_infos)
  repo = AuthenticationRepo(repo_path)
  if os.path.isdir(repo_path):
    if repo.is_git_repository:
      print('Repository {} already exists'.format(repo_path))
      return

  tuf.repository_tool.METADATA_STAGED_DIRECTORY_NAME = METADATA_DIRECTORY_NAME
  repository = create_new_repository(repo_path)
  for role_name, key_info in roles_key_infos.items():
    num_of_keys = key_info.get('number', 1)
    passwords = key_info.get('passwords', [None] * num_of_keys)
    threshold = key_info.get('threshold', 1)
    is_yubikey = key_info.get('yubikey', False)
    role_obj = _role_obj(role_name, repository)
    role_obj.threshold = threshold
    for key_num in range(num_of_keys):
      key_name = _get_key_name(role_name, key_num, num_of_keys)
      if is_yubikey:
        print('Genarating keys for {}'.format(key_name))
        use_existing = False
        if len(yubikeys) > 1 or (len(yubikeys) == 1 and role_name not in yubikeys):
          use_existing = input('Do you want to reuse alredy set up YubiKey? y/n ') == 'y'
          if use_existing:
            key = None
            key_id_certs = {}
            while key is None:
              for existing_role_name, role_keys in yubikeys.items():
                if existing_role_name == role_name:
                  continue
                print(existing_role_name)
                for key_and_cert in role_keys.values():
                  key, cert_cn = key_and_cert
                  key_id_certs[key['keyid']] = cert_cn
                  print('{} id: {}'.format(cert_cn, key['keyid']))
              existing_keyid = input("Enter existing YubiKey's id and press ENTER ")
              try:
                key = get_key(existing_keyid)
                cert_cn = key_id_certs[existing_keyid]
              except UnknownKeyError:
                pass
        if not use_existing:
          input("Please insert a new YubiKey and press ENTER.")
          serial_num = yk_serial_num()
          while serial_num in yubikeys[role_name]:
            print("YubikKy with serial number {} is already in use.\n".format(serial_num))
            input("Please insert new YubiKey and press ENTER.")
            serial_num = yk_serial_num()

          pin = getpass('Enter PIN for {}: '.format(key_name))
          cert_cn = input("Enter key holder's name: ")

          print('Generating keys, please wait...')
          pub_key_pem = yk_setup(pin, cert_cn, cert_exp_days=EXPIRATION_INTERVAL).decode('utf-8')

          key = import_rsakey_from_pem(pub_key_pem)

          cert_path = os.path.join(repo.certs_dir, key['keyid'] + '.cert')
          with open(cert_path, 'wb') as f:
            f.write(sc_export_x509_pem((2,), pin))

        # set Yubikey expiration date
        role_obj.add_verification_key(key, expires=YUBIKEY_EXPIRATION_DATE)
        role_obj.add_external_signature_provider(key, partial(signature_provider,
                                                 key['keyid'], cert_cn))
        yubikeys[role_name][serial_num] = (key, cert_cn)
      else:
        # if keystore exists, load the keys
        # this is useful when generating tests
        if keystore is not None:
          public_key = import_rsa_publickey_from_file(os.path.join(keystore,
                                                                   key_name + '.pub'))
          password = passwords[key_num]
          if password:
            private_key = import_rsa_privatekey_from_file(os.path.join(keystore, key_name),
                                                                       password)
          else:
            private_key = import_rsa_privatekey_from_file(os.path.join(keystore, key_name))
        # if it does not, generate the keys and print the output
        else:
          key = generate_rsa_key()
          print("{} key:\n\n{}\n\n".format(role_name, key['keyval']['private']))
          public_key = private_key = key
        role_obj.add_verification_key(public_key)
        role_obj.load_signing_key(private_key)
  repository.writeall()
  if commit_message is not None and len(commit_message):
    auth_repo = GitRepository(repo_path)
    auth_repo.init_repo()
    auth_repo.commit(commit_message)


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
  roles_key_infos = _read_input_dict(roles_key_infos)
  for role_name, key_info in roles_key_infos.items():
    num_of_keys = key_info.get('number', 1)
    bits = key_info.get('length', 3072)
    passwords = key_info.get('passwords', [''] * num_of_keys)
    is_yubikey = key_info.get('yubikey', False)
    for key_num in range(num_of_keys):
      if not is_yubikey:
        key_name = _get_key_name(role_name, key_num, num_of_keys)
        password = passwords[key_num]
        generate_and_write_rsa_keypair(os.path.join(keystore, key_name), bits=bits,
                                       password=password)


def generate_repositories_json(repo_path, targets_directory, namespace='',
                               targets_relative_dir=None, custom_data=None):
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
  custom_data = _read_input_dict(custom_data)
  repositories = {}
  auth_repo_targets_dir = os.path.join(repo_path, TARGETS_DIRECTORY_NAME)
  for target_repo_dir in os.listdir(targets_directory):
    repo_path = os.path.join(targets_directory, target_repo_dir)
    if not os.path.isdir(repo_path):
      continue
    target_repo = GitRepository(repo_path)
    if not target_repo.is_git_repository:
      continue
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
        url = os.path.relpath(str(target_repo.repo_path), str(targets_relative_dir))
      else:
        url = target_repo.repo_path
      # convert to posix path
      url = pathlib.Path(url).as_posix()
    repositories[target_repo_namespaced_name] = {'urls': [url]}
    if target_repo_namespaced_name in custom_data:
      repositories[target_repo_namespaced_name]['custom'] = custom_data[target_repo_namespaced_name]

  with open(os.path.join(auth_repo_targets_dir, 'repositories.json'), 'w') as f:
    json.dump({'repositories': repositories}, f,  indent=4)


def _get_key_name(role_name, key_num, num_of_keys):
  if num_of_keys == 1:
    return role_name
  else:
    return role_name + str(key_num + 1)


def init_repo(repo_path, targets_directory, namespace, targets_relative_dir,
              keystore, roles_key_infos, targets_key_slot=2,
              repos_custom=None, commit=None):
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
    commit_message:
      If provided, the changes will be committed automatically using the specified message
  """
  # read the key infos here, no need to read the file multiple times
  roles_key_infos = _read_input_dict(roles_key_infos)
  create_repository(repo_path, keystore, roles_key_infos, "Initial metadata")
  add_target_repos(repo_path, targets_directory, namespace)
  generate_repositories_json(repo_path, targets_directory, namespace,
                             targets_relative_dir, repos_custom)
  register_target_files(repo_path, keystore, roles_key_infos, targets_key_slot, commit_msg=commit)


def _load_role_key_from_keys_dict(role, roles_key_infos):
  password = None
  if roles_key_infos is not None and len(roles_key_infos):
    if role in roles_key_infos:
      password = roles_key_infos[role].get('passwords', [None])[0] or None
  return password


def register_target_file(repo_path, file_path, keystore, roles_key_infos,
                         targets_key_slot=2):
  roles_key_infos = _read_input_dict(roles_key_infos)
  taf_repo = Repository(repo_path)
  taf_repo.add_existing_target(file_path)

  _write_targets_metadata(taf_repo, keystore, roles_key_infos,
                          targets_key_slot)


def _read_input_dict(value):
  if value is None:
    return {}
  if type(value) is str:
    if os.path.isfile(value):
      with open(value) as f:
        value = json.loads(f.read())
    else:
      value = json.loads(value)
  return value


def register_target_files(repo_path, keystore, roles_key_infos, targets_key_slot=2,
                          commit_msg=None):
  """
  <Purpose>
    Register all files found in the target directory as targets - updates the targets
    metadata file, snapshot and timestamp. Sign targets
    with yubikey if keystore is not provided
  <Arguments>
    repo_path:
      Authentication repository's path
    keystore:
      Location of the keystore files
    roles_key_infos:
      A dictionary whose keys are role names, while values contain information about the keys.
    targets_key_slot(tuple|int):
      Slot with key on a smart card used for signing
    commit_msg:
      Commit message. If specified, the changes made to the authentication are committed.
  """
  roles_key_infos = _read_input_dict(roles_key_infos)
  repo_path = Path(repo_path).resolve()
  targets_path = repo_path / TARGETS_DIRECTORY_NAME
  taf_repo = Repository(str(repo_path))
  for root, _, filenames in os.walk(str(targets_path)):
    for filename in filenames:
      taf_repo.add_existing_target(str(Path(root) / filename))
  _write_targets_metadata(taf_repo, keystore, roles_key_infos,
                          targets_key_slot)
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


def signature_provider(key_id, cert_cn, data):
  key_slot = (2,)
  key_pin = None
  def _check_key_id(expected_key_id):
    try:
      nonlocal key_pin
      key_pin = getpass(
        "Please insert {} YubiKey, input PIN and press ENTER.\n".format(cert_cn))
      inserted_key = get_yubikey_public_key(key_slot, key_pin)
      return expected_key_id == inserted_key['keyid']
    except Exception:
      return False

  while not _check_key_id(key_id):
    pass

  data = securesystemslib.formats.encode_canonical(data)
  signature = sc_sign_rsa_pkcs_pss_sha256(data, key_slot, key_pin)

  return {
      'keyid': key_id,
      'sig': hexlify(signature).decode()
  }

def update_metadata_expiration_date(repo_path, keystore, roles_key_infos, role,
                                    start_date=datetime.datetime.now(), interval=None, commit_msg=None):
  roles_key_infos = _read_input_dict(roles_key_infos)
  taf_repo = Repository(repo_path)
  update_methods = {'timestamp': taf_repo.update_timestamp,
                    'snapshot': taf_repo.update_snapshot,
                    'targets': taf_repo.update_targets_from_keystore}
  password = _load_role_key_from_keys_dict(role, roles_key_infos)
  update_methods[role](keystore, password, start_date, interval)

  if commit_msg is not None:
    auth_repo = GitRepository(repo_path)
    auth_repo.commit(commit_msg)


def _write_targets_metadata(taf_repo, keystore, roles_key_infos, targets_key_slot=None):

  if keystore is not None:
    # load all keys from keystore files
    # convenient when generating test repositories
    # not recommended in production
    targets_password = _load_role_key_from_keys_dict('targets', roles_key_infos)
    targets_key = load_role_key(keystore, 'targets', targets_password)
    taf_repo.update_targets_from_keystore(targets_key, write=False)
    snapshot_password = _load_role_key_from_keys_dict('snapshot', roles_key_infos)
    timestamp_password = _load_role_key_from_keys_dict('timestamp', roles_key_infos)
    timestamp_key = load_role_key(keystore, 'timestamp', timestamp_password)
    snapshot_key = load_role_key(keystore, 'snapshot', snapshot_password)
  else:
    targets_key_pin = getpass('Please insert targets YubiKey, input PIN and press ENTER.')
    taf_repo.update_targets(targets_key_slot, targets_key_pin, write=False)
    snapshot_pem = getpass('Enter snapshot key')
    snapshot_pem = _form_private_pem(snapshot_pem)
    snapshot_key = import_rsakey_from_pem(snapshot_pem)
    timestamp_pem = getpass('Enter timestamp key')
    timestamp_pem = _form_private_pem(timestamp_pem)
    timestamp_key = import_rsakey_from_pem(timestamp_pem)
  taf_repo.update_snapshot_and_timestmap(snapshot_key, timestamp_key, write=False)
  taf_repo.writeall()

def _form_private_pem(pem):
  return '-----BEGIN RSA PRIVATE KEY-----\n{}\n-----END RSA PRIVATE KEY-----'.format(pem)

# TODO Implement update of repositories.json (updating urls, custom data, adding new repository, removing
# repository etc.)
# TODO create tests for this
