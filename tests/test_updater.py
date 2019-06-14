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


def test_valid_update_no_client_repo(updater_valid_test_repositories, origin_dir, client_dir):
  clients_auth_repo_path = client_dir / 'organization/auth_repo'
  origin_auth_repo_path = updater_valid_test_repositories['organization/auth_repo']
  update_repository(str(origin_auth_repo_path), str(clients_auth_repo_path), str(client_dir), True)
  origin_dir = origin_dir / 'test-updater-valid'
  _check_if_commits_match(updater_valid_test_repositories, origin_dir, client_dir)


def test_valid_update_existing_client_repo(updater_valid_test_repositories, origin_dir, client_dir):
  # clone the origin repositories
  # revert them to an older commit
  origin_dir = origin_dir / 'test-updater-valid'
  client_repos = _clone_and_revert_client_repositories(updater_valid_test_repositories,
                                                       origin_dir, client_dir, 3)
  start_head_shas = {repo_rel_path: repo.head_commit_sha()
                     for repo_rel_path, repo in client_repos.items()}

  clients_auth_repo_path = client_dir / 'organization/auth_repo'
  origin_auth_repo_path = updater_valid_test_repositories['organization/auth_repo']
  update_repository(str(origin_auth_repo_path), str(clients_auth_repo_path), str(client_dir), True)
  _check_if_commits_match(updater_valid_test_repositories, origin_dir, client_dir, start_head_shas)


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


def _clone_and_revert_client_repositories(repositories, origin_dir, client_dir, num_of_commits):
  client_repos = {}

  client_auth_repo = _clone_client_repo('organization/auth_repo', origin_dir, client_dir)
  client_auth_repo.reset_num_of_commits(num_of_commits, True)
  client_auth_repo_head_sha = client_auth_repo.head_commit_sha()
  client_repos['organization/auth_repo'] = client_auth_repo

  _create_last_validated_commit(client_dir, client_auth_repo_head_sha)

  for repository_rel_path in repositories:
    if repository_rel_path == 'organization/auth_repo':
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
