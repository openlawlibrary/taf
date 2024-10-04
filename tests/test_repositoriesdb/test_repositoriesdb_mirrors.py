import taf.repositoriesdb as repositoriesdb
from taf.auth_repo import AuthenticationRepository
from taf.tests.test_repositoriesdb.conftest import load_repositories

AUTH_REPO_NAME = "organization/auth_repo"

REPOS_URLS = {
    f"namespace/{repo_name}": [
        f"https://github.com/namespace/{repo_name}.git",
        f"https://github.com/test/namespace-{repo_name}.git",
        f"https://gitlab.com/namespace2/{repo_name}.git",
        f"https://gitlab.com/namespace/namespace--{repo_name}.git",
        f"git@github.com:namespace/{repo_name}.git",
    ]
    for repo_name in ["TargetRepo1", "TargetRepo2", "TargetRepo3"]
}


def test_load_repositories_with_mirrors(repositoriesdb_test_repositories):
    repositories = repositoriesdb_test_repositories["test-delegated-roles-with-mirrors"]
    auth_repo = AuthenticationRepository(path=repositories[AUTH_REPO_NAME])
    commit = auth_repo.head_commit_sha()
    with load_repositories(auth_repo):
        for repo_path in repositories:
            loaded_repos_dict = repositoriesdb._repositories_dict[auth_repo.path][
                commit
            ]
            if repo_path != AUTH_REPO_NAME:
                repo = loaded_repos_dict[repo_path]
                assert repo.urls == REPOS_URLS[repo_path]
