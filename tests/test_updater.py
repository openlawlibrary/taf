import shutil
import os
import pytest
import taf.settings as settings
from pathlib import Path
from taf.git import GitRepository, NamedGitRepository
from taf.updater.auth_repo import AuthenticationRepo
from taf.updater.updater import update_repository, update_named_repository
from pytest import fixture
from taf.utils import on_rm_error
from taf.exceptions import UpdateFailedError


AUTH_REPO_REL_PATH = 'organization/auth_repo'
TARGET1_SHA_MISMATCH = 'Mismatch between target commits specified in authentication repository and target repository namespace/TargetRepo1'
NO_WORKING_MIRROS = 'Validation of authentication repository auth_repo failed due to error: No working mirror was found'
TIMESTAMP_EXPIRED = "Metadata 'timestamp' expired"
REPLAYED_METADTA = 'ReplayedMetadataError'
settings.update_from_filesystem = True

@fixture(autouse=True)
def run_around_tests(client_dir):
    yield
    for root, dirs, files in os.walk(str(client_dir)):
      for dir_name in dirs:
        shutil.rmtree(str(Path(root) / dir_name), onerror=on_rm_error)


@pytest.mark.parametrize('test_name', ['test-updater-valid', 'test-updater-additional-target-commit',
                                       'test-updater-valid-with-updated-expiration-dates'])
def test_valid_update_no_client_repo(test_name, updater_repositories, origin_dir, client_dir):
  updater_valid_test_repositories = updater_repositories[test_name]
  clients_auth_repo_path = client_dir / AUTH_REPO_REL_PATH
  origin_auth_repo_path = updater_valid_test_repositories[AUTH_REPO_REL_PATH]
  update_repository(str(origin_auth_repo_path), str(clients_auth_repo_path), str(client_dir), True)
  origin_dir = origin_dir / test_name
  _check_if_commits_match(updater_valid_test_repositories, origin_dir, client_dir)
  _chekc_last_validated_commit(clients_auth_repo_path)


@pytest.mark.parametrize('test_name, num_of_commits_to_revert', [('test-updater-valid', 3),
                         ('test-updater-additional-target-commit', 1)])
def test_valid_update_existing_client_repos(test_name, num_of_commits_to_revert,
                                            updater_repositories, origin_dir, client_dir):
  # clone the origin repositories
  # revert them to an older commit
  updater_valid_test_repositories = updater_repositories[test_name]
  origin_dir = origin_dir / test_name
  client_repos = _clone_and_revert_client_repositories(updater_valid_test_repositories,
                                                       origin_dir, client_dir, num_of_commits_to_revert)
  # create valid last validated commit file
  _create_last_validated_commit(client_dir, client_repos[AUTH_REPO_REL_PATH].head_commit_sha())
  _update_and_check_commit_shas(client_repos, updater_valid_test_repositories, origin_dir,
                                client_dir)


def test_no_update_necessary(updater_repositories, origin_dir, client_dir):
  # clone the origin repositories
  # revert them to an older commit
  updater_valid_test_repositories = updater_repositories['test-updater-valid']
  origin_dir = origin_dir / 'test-updater-valid'
  client_repos = _clone_client_repositories(updater_valid_test_repositories,
                                            origin_dir, client_dir)
  # create valid last validated commit file
  _create_last_validated_commit(client_dir, client_repos[AUTH_REPO_REL_PATH].head_commit_sha())
  _update_and_check_commit_shas(client_repos, updater_valid_test_repositories, origin_dir,
                                client_dir)


@pytest.mark.parametrize('test_name, expected_error', [
                        ('test-updater-invalid-target-sha', TARGET1_SHA_MISMATCH),
                        ('test-updater-missing-target-commit', TARGET1_SHA_MISMATCH),
                        ('test-updater-wrong-key', NO_WORKING_MIRROS),
                        ('test-updater-invalid-expiration-date', TIMESTAMP_EXPIRED),
                        ('test-updater-invalid-version-number', REPLAYED_METADTA)])
def test_updater_invalid_update(test_name, expected_error, updater_repositories, origin_dir, client_dir):
  repositories = updater_repositories[test_name]
  clients_auth_repo_path = client_dir / AUTH_REPO_REL_PATH
  origin_auth_repo_path = repositories[AUTH_REPO_REL_PATH]
  _update_invalid_repos_and_check_if_repos_exist(client_dir, repositories, expected_error)


@pytest.mark.parametrize('test_name, expected_error', [
                        ('test-updater-invalid-target-sha', TARGET1_SHA_MISMATCH)])
def test_updater_invalid_target_sha_existing_client_repos(test_name, expected_error,
                                                          updater_repositories, origin_dir,
                                                          client_dir):
  repositories = updater_repositories[test_name]
  clients_auth_repo_path = client_dir / AUTH_REPO_REL_PATH
  origin_dir = origin_dir / test_name
  origin_auth_repo_path = repositories[AUTH_REPO_REL_PATH]
  client_repos = _clone_and_revert_client_repositories(repositories,
                                                       origin_dir, client_dir, 1)
  _create_last_validated_commit(client_dir, client_repos[AUTH_REPO_REL_PATH].head_commit_sha())
  _update_invalid_repos_and_check_if_remained_same(client_repos, client_dir,
                                                   repositories,
                                                   expected_error)


def _chekc_last_validated_commit(clients_auth_repo_path):
  # check if last validated commit is created and the saved commit is correct
  client_auth_repo = AuthenticationRepo(str(clients_auth_repo_path), 'metadata', 'targets')
  head_sha = client_auth_repo.head_commit_sha()
  last_validated_commit = client_auth_repo.last_validated_commit
  assert head_sha == last_validated_commit


def _check_if_commits_match(repositories, origin_dir, client_dir, start_head_shas=None):
  for repository_rel_path in repositories:
    origin_repo = GitRepository(origin_dir / repository_rel_path)
    client_repo = GitRepository(client_dir / repository_rel_path)
    if start_head_shas is not None:
      start_commit = start_head_shas.get(repository_rel_path)
    else:
      start_commit = None
    origin_auth_repo_commits = origin_repo.all_commits_since_commit(start_commit)
    client_auth_repo_commits = client_repo.all_commits_since_commit(start_commit)
    for origin_commit, client_commit in zip(origin_auth_repo_commits, client_auth_repo_commits):
      assert origin_commit == client_commit


def _clone_client_repositories(repositories, origin_dir, client_dir):
  client_repos = {}
  for repository_rel_path in repositories:
    client_repo = _clone_client_repo(repository_rel_path, origin_dir, client_dir)
    client_repos[repository_rel_path] = client_repo
  return client_repos


def _clone_and_revert_client_repositories(repositories, origin_dir, client_dir, num_of_commits):
  client_repos = {}

  client_auth_repo = _clone_client_repo(AUTH_REPO_REL_PATH, origin_dir, client_dir)
  client_auth_repo.reset_num_of_commits(num_of_commits, True)
  client_auth_repo_head_sha = client_auth_repo.head_commit_sha()
  client_repos[AUTH_REPO_REL_PATH] = client_auth_repo

  for repository_rel_path in repositories:
    if repository_rel_path == AUTH_REPO_REL_PATH:
      continue

    client_repo = _clone_client_repo(repository_rel_path, origin_dir, client_dir)
    # read the commit sha stored in target files
    commit = client_auth_repo.get_json(client_auth_repo_head_sha,
                                       str((Path('targets') / repository_rel_path).as_posix()))
    commit_sha = commit['commit']
    client_repo.reset_to_commit(commit_sha, True)
    client_repos[repository_rel_path] = client_repo

  return client_repos


def _clone_client_repo(repository_rel_path, origin_dir, client_dir):
  origin_repo_path = str(origin_dir / repository_rel_path)
  client_repo_path = str(client_dir / repository_rel_path)
  client_repo = GitRepository(client_repo_path, [origin_repo_path])
  client_repo.clone()
  return client_repo


def _create_last_validated_commit(client_dir, client_auth_repo_head_sha):
  client_conf_repo = client_dir / 'organization/_auth_repo'
  client_conf_repo.mkdir(parents=True, exist_ok=True)
  with open(str(client_conf_repo/'last_validated_commit'), 'w') as f:
    f.write(client_auth_repo_head_sha)


def _update_and_check_commit_shas(client_repos, repositories, origin_dir, client_dir):
  start_head_shas = {repo_rel_path: repo.head_commit_sha()
                     for repo_rel_path, repo in client_repos.items()}

  clients_auth_repo_path = client_dir / AUTH_REPO_REL_PATH
  origin_auth_repo_path = repositories[AUTH_REPO_REL_PATH]
  update_repository(str(origin_auth_repo_path), str(clients_auth_repo_path), str(client_dir), True)
  _check_if_commits_match(repositories, origin_dir, client_dir, start_head_shas)
  _chekc_last_validated_commit(clients_auth_repo_path)


def _update_invalid_repos_and_check_if_remained_same(client_repos, client_dir, repositories,
                                                     expected_error):

  start_head_shas = {repo_rel_path: repo.head_commit_sha()
                      for repo_rel_path, repo in client_repos.items()}
  clients_auth_repo_path = client_dir / AUTH_REPO_REL_PATH
  origin_auth_repo_path = repositories[AUTH_REPO_REL_PATH]

  with pytest.raises(UpdateFailedError, match=expected_error) as excinfo:
    update_repository(str(origin_auth_repo_path), str(clients_auth_repo_path), str(client_dir), True)
    _check_if_commits_remained_same(client_repos, start_head_shas)
    # all repositories should still have the same head commit
  for repo_path, repo in client_repos.items():
    current_head = repo.head_commit_sha()
    assert current_head == start_head_shas[repo_path]


def _update_invalid_repos_and_check_if_repos_exist(client_dir, repositories, expected_error):

  clients_auth_repo_path = client_dir / AUTH_REPO_REL_PATH
  origin_auth_repo_path = repositories[AUTH_REPO_REL_PATH]
  with pytest.raises(UpdateFailedError, match=expected_error) as excinfo:
    update_repository(str(origin_auth_repo_path), str(clients_auth_repo_path), str(client_dir), True)

  # the client repositories should not exits
  for repository_rel_path in repositories:
    path = client_dir / repository_rel_path
    assert path.exists() is False
