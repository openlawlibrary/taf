from pathlib import Path
from taf.git import GitRepository
from taf.updater.updater import update_repository, update_named_repository

def test_update_no_client_repo(updater_valid_test_repositories, client_dir):
  clients_auth_repo_path = client_dir / 'organization/auth_repo'
  targets_dir = client_dir
  origin_auth_repo_path = updater_valid_test_repositories['organization/auth_repo']
  targets_dir = str(client_dir)
  update_repository(origin_auth_repo_path, clients_auth_repo_path, targets_dir, True)
  # check if the top commits of the client's repositories mathc the
  # top commits of the target repositories
  origin_auth_repo = GitRepository(origin_auth_repo_path)
  client_auth_repo = GitRepository(clients_auth_repo_path)
  assert origin_auth_repo.head_commit_sha() == client_auth_repo.head_commit_sha()
  origin_auth_repo_commits = origin_auth_repo.all_commits_since_commit(None)
  client_auth_repo_commits = origin_auth_repo.all_commits_since_commit(None)
  for origin_commit, client_commit in zip(origin_auth_repo_commits, client_auth_repo_commits):
    assert origin_commit == client_commit

  target_repositories = ['TargetRepo1', 'TargetRepo2', 'TargetRepo3']




