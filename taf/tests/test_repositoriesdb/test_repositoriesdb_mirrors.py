import pytest
import taf.repositoriesdb as repositoriesdb
from taf.tests.test_repositoriesdb.conftest import load_repositories

AUTH_REPO_NAME = "organization/auth_repo"


@pytest.fixture(scope="session")
def repo_urls(target_repos):
    namaespaces_and_names = [
        (target_repo.name.split("/")[0], target_repo.name.split("/")[1])
        for target_repo in target_repos
    ]
    return {
        f"{namespace}/{repo_name}": [
            f"https://github.com/{namespace}/{repo_name}.git",
            f"https://github.com/test_org/{namespace}-{repo_name}.git",
            f"git@github.com:{namespace}/{repo_name}.git",
            f"git@github.com:test_org/{namespace}-{repo_name}.git",
        ]
        for namespace, repo_name in namaespaces_and_names
    }


def test_load_repositories_with_mirrors(
    target_repos, auth_repo_with_targets, repo_urls
):
    commit = auth_repo_with_targets.head_commit()
    with load_repositories(auth_repo_with_targets):
        for target_repo in target_repos:
            loaded_repos_dict = repositoriesdb._repositories_dict[
                auth_repo_with_targets.path
            ][commit]
            repo = loaded_repos_dict[target_repo.name]
            assert repo.urls == repo_urls[target_repo.name]
