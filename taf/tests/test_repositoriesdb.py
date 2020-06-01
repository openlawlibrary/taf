import taf.repositoriesdb as repositoriesdb
from taf.auth_repo import AuthenticationRepo
import taf.settings as settings
from contextlib import contextmanager

AUTH_REPO_NAME = 'organization/auth_repo'


def setup_module(module):
    settings.update_from_filesystem = True


def teardown_module(module):
    settings.update_from_filesystem = False


def test_load_repositories(repositoriesdb_test_repositories):
    repositories = repositoriesdb_test_repositories["test-delegated-roles"]
    auth_repo = AuthenticationRepo(repositories[AUTH_REPO_NAME])
    with load_repositories(auth_repo):
        _check_repositories_dict(repositories, auth_repo, auth_repo.head_commit_sha())


def test_load_repositories_of_roles(repositoriesdb_test_repositories):
    repositories = repositoriesdb_test_repositories["test-delegated-roles"]
    auth_repo = AuthenticationRepo(repositories[AUTH_REPO_NAME])
    roles = ["delegated_role1"]
    with load_repositories(auth_repo, roles=roles):
        _check_repositories_dict(repositories, auth_repo, auth_repo.head_commit_sha(), roles=roles)


def test_load_repositories_all_commits(repositoriesdb_test_repositories):
    repositories = repositoriesdb_test_repositories["test-delegated-roles"]
    auth_repo = AuthenticationRepo(repositories[AUTH_REPO_NAME])
    commits = auth_repo.all_commits_on_branch()[1:] # remove the first commit
    with load_repositories(auth_repo, commits=commits):
        _check_repositories_dict(repositories, auth_repo, *commits)


def _check_repositories_dict(repositories, auth_repo, *commits, roles=None):
    assert auth_repo.name in repositoriesdb._repositories_dict
    auth_repos_dict = repositoriesdb._repositories_dict[auth_repo.name]
    target_files_of_roles = auth_repo.get_singed_target_files_of_roles(roles)
    for commit in commits:
        assert commit in auth_repos_dict
        for repo_name in repositories:
            if repo_name != AUTH_REPO_NAME:
                if repo_name in target_files_of_roles:
                    assert repo_name in auth_repos_dict[commit]
                else:
                    assert repo_name not in auth_repos_dict[commit]


@contextmanager
def load_repositories(auth_repo, **kwargs):
    repositoriesdb.load_repositories(auth_repo, **kwargs)
    yield
    repositoriesdb.clear_repositories_db()
