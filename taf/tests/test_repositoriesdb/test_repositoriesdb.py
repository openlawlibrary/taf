import pytest
import taf.repositoriesdb as repositoriesdb
import taf.settings as settings
from taf.tests.test_repositoriesdb.conftest import load_repositories

AUTH_REPO_NAME = "organization/auth_repo"


def setup_module(module):
    settings.update_from_filesystem = True


def teardown_module(module):
    settings.update_from_filesystem = False


def test_load_repositories_when_no_delegations(target_repos, auth_repo_with_targets):
    with load_repositories(auth_repo_with_targets):
        _check_repositories_dict(
            target_repos,
            auth_repo_with_targets,
            auth_repo_with_targets.head_commit(),
        )


def test_load_repositories_only_load_targets(target_repos, auth_repo_with_targets):
    with load_repositories(auth_repo_with_targets):
        _check_repositories_dict(
            target_repos,
            auth_repo_with_targets,
            auth_repo_with_targets.head_commit(),
            only_load_targets=True,
        )


def test_load_repositories_of_roles(target_repos, auth_repo_with_targets):
    roles = ["delegated_role"]
    with load_repositories(auth_repo_with_targets, roles=roles):
        _check_repositories_dict(
            target_repos,
            auth_repo_with_targets,
            auth_repo_with_targets.head_commit(),
            roles=roles,
        )


def test_load_repositories_all_commits(target_repos, auth_repo_with_targets):
    commits = auth_repo_with_targets.all_commits_on_branch()[
        2:
    ]  # remove the first commit
    with load_repositories(auth_repo_with_targets, commits=commits):
        _check_repositories_dict(target_repos, auth_repo_with_targets, *commits)


def test_get_deduplicated_repositories(target_repos, auth_repo_with_targets):
    commits = auth_repo_with_targets.all_commits_on_branch()[
        1:
    ]  # remove the first commit
    with load_repositories(auth_repo_with_targets, commits=commits):
        repos = repositoriesdb.get_deduplicated_repositories(
            auth_repo_with_targets, commits
        )
        assert len(repos) == 3
        for target_repo in target_repos:
            assert target_repo.name in repos


def test_get_repository(target_repos, auth_repo_with_targets):
    commits = auth_repo_with_targets.all_commits_on_branch()[1:]
    with load_repositories(auth_repo_with_targets, commits=commits):
        for target_repo in target_repos:
            repo = repositoriesdb.get_repository(
                auth_repo_with_targets, target_repo.name, commits[-1]
            )
            assert repo.name == target_repo.name


def test_get_repository_by_custom_data(target_repos, auth_repo_with_targets):
    with load_repositories(auth_repo_with_targets):
        repo_types = ("type1", "type2", "type3")
        for repo_type, repo in zip(repo_types, target_repos):
            type_repos = repositoriesdb.get_repositories_by_custom_data(
                auth_repo_with_targets, type=repo_type
            )
            assert len(type_repos) == 1
            assert type_repos[0].name == repo.name


def test_get_repositories_paths_by_custom_data(target_repos, auth_repo_with_targets):
    repo_types = ("type1", "type2", "type3")
    for repo_type, repo in zip(repo_types, target_repos):
        paths = repositoriesdb.get_repositories_paths_by_custom_data(
            auth_repo_with_targets, type=repo_type
        )
        assert paths == [repo.name]


def test_dangerous_filter_expressions_are_blocked():
    """Test that dangerous filter expressions raise ValueError."""

    dangerous_expressions = [
        "__import__('os').system('echo pwned')",
        "().__class__.__bases__[0].__subclasses__()",
        "repo.__class__.__init__.__globals__",
        "[__import__('os') for x in [1]][0]",
        "(lambda: __import__('os').system('ls'))()",
        "exec('print(1)')",
        "compile('print(1)', '<string>', 'exec')",
        "globals()",
        "locals()",
        "__import__('subprocess').run(['ls'])",
    ]

    for expr in dangerous_expressions:
        with pytest.raises(ValueError):
            repositoriesdb._validate_filter_expression(expr)


def test_safe_filter_expressions_are_allowed():
    """Test that safe filter expressions do not raise errors."""

    safe_expressions = [
        "repo['type'] == 'html'",
        "repo['type'] != 'html'",
        "repo.get('serve') == 'latest'",
        "repo.get('serve') == 'historical'",
        "not repo.get('archived')",
        "repo['type'] == 'html' and repo['serve'] == 'latest'",
        "repo['type'] == 'html' or repo.get('archived')",
        "repo.get('nonexistent', 'default') == 'default'",
        "'type' in repo",
        "repo.get('archived') is None",
    ]

    for expr in safe_expressions:
        # Should not raise
        repositoriesdb._validate_filter_expression(expr)


def test_filter_repositories(target_repos, auth_repo_with_targets):
    with load_repositories(auth_repo_with_targets):
        repo_types = ("type1", "type2", "type3")
        for repo_type, repo in zip(repo_types, target_repos):
            filter_exp = f"repo['type']=='{repo_type}'"
            repos = repositoriesdb.get_repositories_by_expression(
                auth_repo_with_targets, filter_expr=filter_exp
            )
            assert len(repos) == 1
            assert repo.name in repos


def test_get_repositories_names_by_expression(target_repos, auth_repo_with_targets):
    repo_types = ("type1", "type2", "type3")
    for repo_type, repo in zip(repo_types, target_repos):
        filter_exp = f"repo['type']=='{repo_type}'"
        names = repositoriesdb.get_repository_names_by_expression(
            auth_repo_with_targets, filter_expr=filter_exp
        )
        assert names == [repo.name]

    filter_exp = "repo['type'] in ('type1', 'type2')"
    names = repositoriesdb.get_repository_names_by_expression(
        auth_repo_with_targets, filter_expr=filter_exp
    )
    assert len(names) == 2
    assert names == ["test_repositoriesdb/target1", "test_repositoriesdb/target2"]


def _check_repositories_dict(
    target_repos, auth_repo, *commits, roles=None, only_load_targets=False
):
    assert auth_repo.path in repositoriesdb._repositories_dict
    auth_repos_dict = repositoriesdb._repositories_dict[auth_repo.path]
    if roles is not None and len(roles):
        only_load_targets = True
    if only_load_targets:
        target_files_of_roles = auth_repo.get_signed_target_files_of_roles(roles)
    for commit in commits:
        repositories_json = auth_repo.get_json(
            commit, repositoriesdb.REPOSITORIES_JSON_PATH
        )
        repositories_data = repositories_json["repositories"]
        assert commit in auth_repos_dict
        for target_repo in target_repos:
            repo_name = target_repo.name
            if not only_load_targets or (
                only_load_targets and repo_name in target_files_of_roles
            ):
                assert repo_name in auth_repos_dict[commit]
                # check custom data
                custom_data = repositories_data[repo_name].get("custom", {})
                assert auth_repos_dict[commit][repo_name].custom == custom_data
            else:
                assert repo_name not in auth_repos_dict[commit]
