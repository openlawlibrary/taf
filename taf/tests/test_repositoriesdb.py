import pytest
import taf.repositoriesdb as repositoriesdb
from taf.auth_repo import AuthenticationRepo
import taf.settings as settings
from taf.tests.conftest import load_repositories

AUTH_REPO_NAME = "organization/auth_repo"


def setup_module(module):
    settings.update_from_filesystem = True


def teardown_module(module):
    settings.update_from_filesystem = False


@pytest.mark.parametrize(
    "test_name",
    [
        "test-no-delegations",
        "test-delegated-roles",
        "test-delegated-roles-with-mirrors",
    ],
)
def test_load_repositories(test_name, repositoriesdb_test_repositories):
    repositories = repositoriesdb_test_repositories[test_name]
    auth_repo = AuthenticationRepo(repositories[AUTH_REPO_NAME])
    with load_repositories(auth_repo):
        _check_repositories_dict(repositories, auth_repo, auth_repo.head_commit_sha())


@pytest.mark.parametrize("test_name", ["test-no-delegations", "test-delegated-roles"])
def test_load_repositories_only_load_targets(
    test_name, repositoriesdb_test_repositories
):
    repositories = repositoriesdb_test_repositories[test_name]
    auth_repo = AuthenticationRepo(repositories[AUTH_REPO_NAME])
    with load_repositories(auth_repo, only_load_targets=True):
        _check_repositories_dict(
            repositories, auth_repo, auth_repo.head_commit_sha(), only_load_targets=True
        )


def test_load_repositories_of_roles(repositoriesdb_test_repositories):
    repositories = repositoriesdb_test_repositories["test-delegated-roles"]
    auth_repo = AuthenticationRepo(repositories[AUTH_REPO_NAME])
    roles = ["delegated_role1"]
    with load_repositories(auth_repo, roles=roles):
        _check_repositories_dict(
            repositories, auth_repo, auth_repo.head_commit_sha(), roles=roles
        )


@pytest.mark.parametrize("test_name", ["test-no-delegations", "test-delegated-roles"])
def test_load_repositories_all_commits(test_name, repositoriesdb_test_repositories):
    repositories = repositoriesdb_test_repositories[test_name]
    auth_repo = AuthenticationRepo(repositories[AUTH_REPO_NAME])
    commits = auth_repo.all_commits_on_branch()[1:]  # remove the first commit
    with load_repositories(auth_repo, commits=commits):
        _check_repositories_dict(repositories, auth_repo, *commits)


def test_get_deduplicated_repositories(repositoriesdb_test_repositories):
    repositories = repositoriesdb_test_repositories["test-delegated-roles"]
    auth_repo = AuthenticationRepo(repositories[AUTH_REPO_NAME])
    commits = auth_repo.all_commits_on_branch()[1:]  # remove the first commit
    with load_repositories(auth_repo, commits=commits):
        repos = repositoriesdb.get_deduplicated_repositories(auth_repo, commits)
        assert len(repos) == 3
        for repo_name in repositories:
            if repo_name != AUTH_REPO_NAME:
                assert repo_name in repos


def test_get_repository(repositoriesdb_test_repositories):
    repositories = repositoriesdb_test_repositories["test-delegated-roles"]
    auth_repo = AuthenticationRepo(repositories[AUTH_REPO_NAME])
    commits = auth_repo.all_commits_on_branch()[1:]  # remove the first commit
    path = "namespace/TargetRepo1"
    with load_repositories(auth_repo, commits=commits):
        repo = repositoriesdb.get_repository(auth_repo, path, commits[-1])
        assert repo.name == path
        repo = repositoriesdb.get_repository(auth_repo, path, commits[-2])
        assert repo.name == path


def test_get_repository_by_custom_data(repositoriesdb_test_repositories):
    repositories = repositoriesdb_test_repositories["test-delegated-roles"]
    auth_repo = AuthenticationRepo(repositories[AUTH_REPO_NAME])
    with load_repositories(auth_repo):
        for repo_type, repo_name in [
            ("type1", "namespace/TargetRepo1"),
            ("type2", "namespace/TargetRepo2"),
            ("type3", "namespace/TargetRepo3"),
        ]:
            type_repos = repositoriesdb.get_repositories_by_custom_data(
                auth_repo, type=repo_type
            )
            assert len(type_repos) == 1
            assert type_repos[0].name == repo_name


def test_get_repositories_paths_by_custom_data(repositoriesdb_test_repositories):
    repositories = repositoriesdb_test_repositories["test-delegated-roles"]
    auth_repo = AuthenticationRepo(repositories[AUTH_REPO_NAME])
    with load_repositories(auth_repo):
        for repo_type, repo_name in [
            ("type1", "namespace/TargetRepo1"),
            ("type2", "namespace/TargetRepo2"),
            ("type3", "namespace/TargetRepo3"),
        ]:
            paths = repositoriesdb.get_repositories_paths_by_custom_data(
                auth_repo, type=repo_type
            )
            assert paths == [repo_name]


def _check_repositories_dict(
    repositories, auth_repo, *commits, roles=None, only_load_targets=False
):
    assert auth_repo.name in repositoriesdb._repositories_dict
    auth_repos_dict = repositoriesdb._repositories_dict[auth_repo.name]
    if roles is not None and len(roles):
        only_load_targets = True
    if only_load_targets:
        target_files_of_roles = auth_repo.get_singed_target_files_of_roles(roles)
    for commit in commits:
        repositories_json = auth_repo.get_json(
            commit, repositoriesdb.REPOSITORIES_JSON_PATH
        )
        repositories_data = repositories_json["repositories"]
        assert commit in auth_repos_dict
        for repo_name in repositories:
            if repo_name != AUTH_REPO_NAME:
                if not only_load_targets or (
                    only_load_targets and repo_name in target_files_of_roles
                ):
                    assert repo_name in auth_repos_dict[commit]
                    # check custom data
                    custom_data = repositories_data[repo_name].get("custom", {})
                    assert (
                        auth_repos_dict[commit][repo_name].additional_info
                        == custom_data
                    )
                else:
                    assert repo_name not in auth_repos_dict[commit]
