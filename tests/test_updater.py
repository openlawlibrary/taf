import shutil
import os
from pathlib import Path
from taf.git import GitRepository, NamedGitRepository
from taf.updater.updater import update_repository, update_named_repository
from pytest import fixture
from taf.utils import on_rm_error

@fixture(autouse=True)
def run_around_tests(client_dir):
    yield
    for root, dirs, files in os.walk(str(client_dir)):
      for dir_name in dirs:
        shutil.rmtree(str(Path(root) / dir_name), onerror=on_rm_error)


def test_update_no_client_repo(updater_valid_test_repositories, origin_dir, client_dir):
  clients_auth_repo_path = client_dir / 'organization/auth_repo'
  targets_dir = client_dir
  origin_auth_repo_path = updater_valid_test_repositories['organization/auth_repo']
  update_repository(str(origin_auth_repo_path), str(clients_auth_repo_path), str(client_dir), True)
  origin_dir = origin_dir / 'test-updater-valid'
  _check_if_commits_match(updater_valid_test_repositories, origin_dir, client_dir)


def _check_if_commits_match(repositories, origin_dir, client_dir):
  for repository_rel_path in repositories:
    origin_repo = GitRepository(origin_dir/repository_rel_path)
    client_repo = GitRepository(client_dir/repository_rel_path)
    origin_auth_repo_commits = origin_repo.all_commits_since_commit(None)
    client_auth_repo_commits = client_repo.all_commits_since_commit(None)
    for origin_commit, client_commit in zip(origin_auth_repo_commits, client_auth_repo_commits):
      assert origin_commit == client_commit
