import shutil
from contextlib import contextmanager
from pathlib import Path

from pytest import fixture, yield_fixture
from taf.repository_tool import load_repository

import oll_sc

from .yubikey import (Root1YubiKey, Root2YubiKey, Root3YubiKey, TargetYubiKey,
                      init_pkcs11_mock)

TEST_DATA_PATH = Path(__file__).parent / 'data'
TEST_DATA_REPOS_PATH = TEST_DATA_PATH / 'repos'
TEST_DATA_ORIGIN_PATH = TEST_DATA_REPOS_PATH / 'origin'
KEYSTORE_PATH = TEST_DATA_PATH / 'keystore'


def pytest_configure(config):
  oll_sc.init_pkcs11 = init_pkcs11_mock


@contextmanager
def origin_repos(repo_paths):
  """Coppies git repository from `data/repos/test-XYZ` to data/repos/origin/XYZ
  path and renames `git` to `.git` for each repository.
  """
  temp_paths = {}

  # Create directories
  for repo_path in repo_paths:
    repo_path_name = repo_path.name
    dst_path = TEST_DATA_ORIGIN_PATH / repo_path_name
    # Copy git repository and rename "git" to ".git"
    shutil.copytree(str(repo_path), str(dst_path))
    (dst_path / 'git').rename(dst_path / '.git')
    temp_paths[repo_path_name] = str(dst_path)

  yield temp_paths

  # Delete directories
  for temp_path in temp_paths.values():
    shutil.rmtree(temp_path)


@yield_fixture(scope='session', autouse=True)
def taf_happy_path():
  """TAF repository for testing."""
  taf_repo_path = TEST_DATA_REPOS_PATH / 'test-happy-path/taf'
  target_dummy_repo_path = TEST_DATA_REPOS_PATH / 'test-happy-path/target_dummy_repo'

  with origin_repos([taf_repo_path, target_dummy_repo_path]) as origins:
    taf_repo_origin_path = origins[taf_repo_path.name]
    with load_repository(taf_repo_origin_path) as taf_repo:
      yield taf_repo


@fixture(scope='session', autouse=True)
def targets_yk():
  """Targets YubiKey."""
  return TargetYubiKey(KEYSTORE_PATH)


@fixture(scope='session', autouse=True)
def root1_yk():
  """Root1 YubiKey."""
  return Root1YubiKey(KEYSTORE_PATH)


@fixture(scope='session', autouse=True)
def root2_yk():
  """Root2 YubiKey."""
  return Root2YubiKey(KEYSTORE_PATH)


@fixture(scope='session', autouse=True)
def root3_yk():
  """Root3 YubiKey."""
  return Root3YubiKey(KEYSTORE_PATH)
