import pytest
from freezegun import freeze_time
from collections import defaultdict
from datetime import datetime
import fnmatch
import json
from taf import repositoriesdb
from taf.auth_repo import AuthenticationRepository
from taf.git import GitRepository
from taf.exceptions import UpdateFailedError
from taf.updater.types.update import OperationType, UpdateType
from taf.updater.updater import RepositoryConfig, clone_repository, update_repository


def check_last_validated_commit(clients_auth_repo_path):
    # check if last validated commit is created and the saved commit is correct
    client_auth_repo = AuthenticationRepository(path=clients_auth_repo_path)
    head_sha = client_auth_repo.head_commit_sha()
    last_validated_commit = client_auth_repo.last_validated_commit
    assert head_sha == last_validated_commit


def check_if_commits_match(
    client_repositories,
    origin_dir,
    start_head_shas=None,
    excluded_target_globs=None,
):
    excluded_target_globs = excluded_target_globs or []
    for repo_name, client_repo in client_repositories.items():
        if any(
            fnmatch.fnmatch(repo_name, excluded_target_glob)
            for excluded_target_glob in excluded_target_globs
        ):
            continue
        origin_repo = GitRepository(origin_dir, repo_name)
        for branch in origin_repo.branches():
            # ensures that git log will work
            client_repo.checkout_branch(branch)
            start_commit = None
            if start_head_shas is not None:
                start_commit = start_head_shas[repo_name].get(branch)
            origin_auth_repo_commits = origin_repo.all_commits_since_commit(
                start_commit, branch=branch
            )
            client_auth_repo_commits = client_repo.all_commits_since_commit(
                start_commit, branch=branch
            )
            for origin_commit, client_commit in zip(
                origin_auth_repo_commits, client_auth_repo_commits
            ):
                assert origin_commit == client_commit


def check_if_last_validated_commit_exists(client_auth_repo, should_exist):
    last_validated_commit = client_auth_repo.last_validated_commit
    if not should_exist:
        assert last_validated_commit is None
    else:
        assert (
            client_auth_repo.top_commit_of_branch(client_auth_repo.default_branch)
            == last_validated_commit
        )


def clone_repositories(
    origin_auth_repo,
    clients_dir,
    expected_repo_type=UpdateType.EITHER,
    excluded_target_globs=None,
):

    config = RepositoryConfig(
        operation=OperationType.CLONE,
        url=str(origin_auth_repo.path),
        update_from_filesystem=True,
        path=None,
        library_dir=str(clients_dir),
        expected_repo_type=expected_repo_type,
        excluded_target_globs=excluded_target_globs,
    )

    with freeze_time(_get_valid_update_time(origin_auth_repo.path)):
        clone_repository(config)


def clone_client_auth_repo_without_updater(origin_auth_repo, client_dir):
    client_repo = GitRepository(
        client_dir, origin_auth_repo.name, urls=[str(origin_auth_repo.path)]
    )
    client_repo.clone()
    assert client_repo.path.is_dir()


def clone_client_target_repos_without_updater(origin_auth_repo, client_dir):
    client_repo = GitRepository(client_dir, origin_auth_repo.name)
    orgin_target_repos = load_target_repositories(origin_auth_repo)
    for target_repo in orgin_target_repos.values():
        client_repo = GitRepository(
            client_dir, target_repo.name, urls=[str(target_repo.path)]
        )
        client_repo.clone()
        assert client_repo.path.is_dir()


def _get_valid_update_time(origin_auth_repo_path):
    # read timestamp.json expiration date
    timestamp_path = origin_auth_repo_path / "metadata" / "timestamp.json"
    timestamp_data = json.loads(timestamp_path.read_text())
    expires = timestamp_data["signed"]["expires"]
    return datetime.strptime(expires, "%Y-%m-%dT%H:%M:%SZ").date().strftime("%Y-%m-%d")


def _get_head_commit_shas(client_repos):
    start_head_shas = defaultdict(dict)
    if client_repos is not None:
        for repo_rel_path, repo in client_repos.items():
            for branch in repo.branches():
                start_head_shas[repo_rel_path][branch] = repo.top_commit_of_branch(
                    branch
                )
    return start_head_shas


def load_target_repositories(
    auth_repo, library_dir=None, excluded_target_globs=None, commits=None
):
    if library_dir is None:
        library_dir = auth_repo.path.parent.parent

    repositoriesdb.load_repositories(
        auth_repo,
        library_dir=library_dir,
        only_load_targets=True,
        excluded_target_globs=excluded_target_globs,
        commits=commits,
    )
    return repositoriesdb.get_deduplicated_repositories(
        auth_repo,
        commits=commits,
    )


def update_and_check_commit_shas(
    operation,
    origin_auth_repo,
    clients_dir,
    expected_repo_type=UpdateType.EITHER,
    auth_repo_name_exists=True,
    excluded_target_globs=None,
):

    client_repos = load_target_repositories(origin_auth_repo, clients_dir)
    client_repos = {
        repo_name: repo
        for repo_name, repo in client_repos.items()
        if repo.path.is_dir()
    }

    clients_auth_repo_path = clients_dir / origin_auth_repo.name
    clients_auth_repo = GitRepository(path=clients_auth_repo_path)
    if clients_auth_repo_path.is_dir():
        client_repos[clients_auth_repo.name] = clients_auth_repo
    start_head_shas = _get_head_commit_shas(client_repos)

    config = RepositoryConfig(
        operation=operation,
        url=str(origin_auth_repo.path),
        update_from_filesystem=True,
        path=str(clients_auth_repo_path) if auth_repo_name_exists else None,
        library_dir=str(clients_dir),
        expected_repo_type=expected_repo_type,
        excluded_target_globs=excluded_target_globs,
    )

    if operation == OperationType.CLONE:
        clone_repository(config)
    else:
        update_repository(config)

    origin_root_dir = origin_auth_repo.path.parent.parent
    check_if_commits_match(
        client_repos,
        origin_root_dir,
        start_head_shas,
        excluded_target_globs,
    )
    if not excluded_target_globs:
        check_last_validated_commit(clients_auth_repo_path)

    if excluded_target_globs:
        repositoriesdb.clear_repositories_db()
        all_target_repositories = load_target_repositories(
            origin_auth_repo, clients_dir
        )
        for target_repo in all_target_repositories.values():
            for excluded_target_glob in excluded_target_globs:
                if fnmatch.fnmatch(target_repo.name, excluded_target_glob):
                    assert not target_repo.path.is_dir()
                    break


def update_invalid_repos_and_check_if_repos_exist(
    operation,
    origin_auth_repo,
    clients_dir,
    expected_error,
    expect_partial_update,
    expected_repo_type=UpdateType.EITHER,
    auth_repo_name_exists=True,
    excluded_target_globs=None,
    strict=False,
):

    client_repos = load_target_repositories(origin_auth_repo, clients_dir)
    clients_auth_repo_path = clients_dir / origin_auth_repo.name
    clients_auth_repo = GitRepository(path=clients_auth_repo_path)
    client_repos[clients_auth_repo.name] = clients_auth_repo
    repositories_which_existed_paths = [
        client_repo.path
        for client_repo in client_repos.values()
        if client_repo.path.is_dir()
    ]

    config = RepositoryConfig(
        operation=operation,
        url=str(origin_auth_repo.path),
        update_from_filesystem=True,
        path=str(clients_auth_repo_path) if auth_repo_name_exists else None,
        library_dir=str(clients_dir),
        expected_repo_type=expected_repo_type,
        excluded_target_globs=excluded_target_globs,
        strict=strict,
    )

    def _update_expect_error():
        with pytest.raises(UpdateFailedError, match=expected_error):
            if operation == OperationType.CLONE:
                clone_repository(config)
            else:
                update_repository(config)

    _update_expect_error()

    if not expect_partial_update:
        # the client repositories should not exits
        for client_repository in client_repos.values():
            if client_repository.path in repositories_which_existed_paths:
                assert client_repository.path.exists()
            else:
                assert not client_repository.path.exists()
