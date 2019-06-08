from tuf.repository_tool import generate_and_write_rsa_keypair, import_rsa_publickey_from_file, \
                                import_rsa_privatekey_from_file, create_new_repository, \
                                METADATA_DIRECTORY_NAME, METADATA_STAGED_DIRECTORY_NAME, \
                                TARGETS_DIRECTORY_NAME
from taf.git import GitRepository
import os
import shutil


def add_target_repos(repository_location, targets_directory, keystore_location, roles_key_infos,
                     namespace=''):
  #TODO this does not update metadata files
  auth_repo_targets_dir = os.path.join(repository_location, TARGETS_DIRECTORY_NAME)
  if namespace:
    auth_repo_targets_dir = os.path.join(auth_repo_targets_dir, namespace)
    if not os.path.exists(auth_repo_targets_dir):
      os.makedirs(auth_repo_targets_dir)
  for target_repo_dir in os.listdir(targets_directory):
    target_repo = GitRepository(os.path.join(targets_directory, target_repo_dir))
    commit = target_repo.head_commit_sha()
    target_repo_name = os.path.basename(target_repo_dir)
    with open(os.path.join(auth_repo_targets_dir, target_repo_name), 'w') as f:
      f.write(commit)


def generate_keys(keystore_location, roles_key_infos):
  """
  <Arguments>
    keystore_location:
      Location where the keystore files should be saved
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
    passwords = key_info['passwords']
    for key_num in range(num_of_keys):
      key_name = _get_key_name(role_name, key_num, num_of_keys)
      password = passwords[key_num]
      generate_and_write_rsa_keypair(os.path.join(keystore_location, key_name), bits=bits,
                                     password=password)


def create_repository(repository_location, keystore_location, roles_key_infos):
  if os.path.isdir(repository_location):
    print('{} already exists'.format(repository_location))
    return
  repository = create_new_repository(repository_location)
  for role_name, key_info in roles_key_infos.items():
    num_of_keys = key_info.get('number', 1)
    passwords = key_info['passwords']
    threshold = key_info.get('threshold', 1)
    role_obj = _role_obj(role_name, repository)
    role_obj.threshold = threshold
    for key_num in range(num_of_keys):
      key_name = _get_key_name(role_name, key_num, num_of_keys)
      public_key = import_rsa_publickey_from_file(os.path.join(keystore_location,
                                                               key_name + '.pub'))
      password = passwords[key_num]
      if password:
        private_key = import_rsa_privatekey_from_file(os.path.join(keystore_location, key_name),
                                                      password)
      else:
        private_key = import_rsa_privatekey_from_file(os.path.join(keystore_location, key_name))
      role_obj.add_verification_key(public_key)
      role_obj.load_signing_key(private_key)
  repository.writeall()
  _move_metadata(repository_location)


def _get_key_name(role_name, key_num, num_of_keys):
  if num_of_keys == 1:
    return role_name
  else:
    return role_name + str(key_num + 1)


def _move_metadata(repository_location):

  staged_dir = os.path.join(repository_location, METADATA_STAGED_DIRECTORY_NAME)
  metadata_dir = os.path.join(repository_location, METADATA_DIRECTORY_NAME)
  shutil.copytree(staged_dir, metadata_dir)
  shutil.rmtree(staged_dir)

def _role_obj(role, repository):
  if role == 'targets':
    return repository.targets
  elif role == 'snapshot':
    return repository.snapshot
  elif role == 'timestamp':
    return repository.timestamp
  elif role == 'root':
    return repository.root
