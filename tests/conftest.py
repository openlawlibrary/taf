import os
import shutil
from contextlib import contextmanager
from pathlib import Path

from pytest import fixture, yield_fixture

import taf.repository_tool as repository_tool
import taf.yubikey
from taf.repository_tool import Repository
from taf.utils import on_rm_error
from tuf.repository_tool import (import_rsa_privatekey_from_file,
                                 import_rsa_publickey_from_file)

from .yubikey_utils import (Root1YubiKey, Root2YubiKey, Root3YubiKey,
                            TargetYubiKey, _yk_piv_ctrl_mock)

TEST_DATA_PATH = Path(__file__).parent / 'data'
TEST_DATA_REPOS_PATH = TEST_DATA_PATH / 'repos'
TEST_DATA_ORIGIN_PATH = TEST_DATA_REPOS_PATH / 'origin'
KEYSTORE_PATH = TEST_DATA_PATH / 'keystore'
WRONG_KEYSTORE_PATH = TEST_DATA_PATH / 'wrong_keystore'
CLIENT_DIR_PATH = TEST_DATA_REPOS_PATH / 'client'


def pytest_configure(config):
  taf.yubikey._yk_piv_ctrl = _yk_piv_ctrl_mock


@contextmanager
def origin_repos_group(test_group_dir):
  all_paths = {}
  test_group_dir = str(TEST_DATA_REPOS_PATH / test_group_dir)
  for test_dir in os.scandir(test_group_dir):
    if test_dir.is_dir():
      all_paths[test_dir.name] = _copy_repos(test_dir.path, test_dir.name)

  yield all_paths

  for test_name in all_paths:
    test_dst_path = str(TEST_DATA_ORIGIN_PATH / test_name)
    shutil.rmtree(test_dst_path, onerror=on_rm_error)


@contextmanager
def origin_repos(test_name):
  """Coppies git repository from `data/repos/test-XYZ` to data/repos/origin/test-XYZ
  path and renames `git` to `.git` for each repository.
  """
  test_dir_path = str(TEST_DATA_REPOS_PATH / test_name)
  temp_paths = _copy_repos(test_dir_path, test_name)

  yield temp_paths

  test_dst_path = str(TEST_DATA_ORIGIN_PATH / test_name)
  shutil.rmtree(test_dst_path, onerror=on_rm_error)


def _copy_repos(test_dir_path, test_name):
  paths = {}
  for root, dirs, _ in os.walk(test_dir_path):
    for dir_name in dirs:
      if dir_name == 'git':
        repo_rel_path = os.path.relpath(root, test_dir_path)
        dst_path = TEST_DATA_ORIGIN_PATH / test_name / repo_rel_path
        # convert dst_path to string in order to support python 3.5
        shutil.copytree(root, str(dst_path))
        (dst_path / 'git').rename(dst_path / '.git')
        repo_rel_path = Path(repo_rel_path).as_posix()
        paths[repo_rel_path] = str(dst_path)
  return paths


@yield_fixture(scope='session', autouse=True)
def taf_happy_path():
  """TAF repository for testing."""
  taf_repo_name = 'taf'
  test_happy_path_dir = 'test-happy-path'
  test_happy_path_pkcs1v15_dir = 'test-happy-path-pkcs1v15'

  with origin_repos(test_happy_path_dir) as origins, \
          origin_repos(test_happy_path_pkcs1v15_dir) as pkcs1v15_origins:

    # Repository using rsassa-pss-sha256 scheme
    # taf_repo_origin_path = origins[taf_repo_name]
    # taf_repo = Repository(taf_repo_origin_path)

    # Repository using rsa-pkcs1v15-sha256 scheme
    taf_repo_pkcs1v15_origin_path = pkcs1v15_origins[taf_repo_name]
    taf_repo_pkcs1v15 = Repository(taf_repo_pkcs1v15_origin_path)

    repository_tool.DISABLE_KEYS_CACHING = True

    yield taf_repo_pkcs1v15


@yield_fixture(scope="session", autouse=True)
def updater_repositories():
  test_dir = 'test-updater'
  with origin_repos_group(test_dir) as origins:
    yield origins


@fixture
def client_dir():
  return CLIENT_DIR_PATH


@fixture
def origin_dir():
  return TEST_DATA_ORIGIN_PATH


@fixture
def keystore():
  """Keystore path."""
  return str(KEYSTORE_PATH)


@fixture
def wrong_keystore():
  """Path of the wrong keystore"""
  return str(WRONG_KEYSTORE_PATH)


@fixture
def targets_yk():
  """Targets YubiKey."""
  return TargetYubiKey(KEYSTORE_PATH)


@fixture
def root1_yk():
  """Root1 YubiKey."""
  return Root1YubiKey(KEYSTORE_PATH)


@fixture
def root2_yk():
  """Root2 YubiKey."""
  return Root2YubiKey(KEYSTORE_PATH)


@fixture
def root3_yk():
  """Root3 YubiKey."""
  return Root3YubiKey(KEYSTORE_PATH)


@fixture
def snapshot_key():
  """Snapshot key."""
  key = import_rsa_publickey_from_file(str(KEYSTORE_PATH / 'snapshot.pub'))
  priv_key = import_rsa_privatekey_from_file(str(KEYSTORE_PATH / 'snapshot'))
  key['keyval']['private'] = priv_key['keyval']['private']
  return key


@fixture
def timestamp_key():
  """Timestamp key."""
  key = import_rsa_publickey_from_file(str(KEYSTORE_PATH / 'timestamp.pub'))
  priv_key = import_rsa_privatekey_from_file(str(KEYSTORE_PATH / 'timestamp'))
  key['keyval']['private'] = priv_key['keyval']['private']
  return key


@fixture
def targets_key():
  """Timestamp key."""
  key = import_rsa_publickey_from_file(str(KEYSTORE_PATH / 'targets.pub'))
  priv_key = import_rsa_privatekey_from_file(str(KEYSTORE_PATH / 'targets'))
  key['keyval']['private'] = priv_key['keyval']['private']
  return key
