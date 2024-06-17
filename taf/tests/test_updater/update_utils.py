from freezegun import freeze_time
from collections import defaultdict
from datetime import datetime
import fnmatch
import json
from pathlib import Path
from taf import repositoriesdb
from taf.auth_repo import AuthenticationRepository
from taf.git import GitRepository
from taf.updater.types.update import OperationType, UpdateType
from taf.updater.updater import RepositoryConfig, clone_repository, update_repository


def check_last_validated_commit(clients_auth_repo_path):
    # check if last validated commit is created and the saved commit is correct
    client_auth_repo = AuthenticationRepository(path=clients_auth_repo_path)
    head_sha = client_auth_repo.head_commit_sha()
    last_validated_commit = client_auth_repo.last_validated_commit
    assert head_sha == last_validated_commit


def check_if_commits_match(
    repositories,
    origin_repo,
    client_repo,
    start_head_shas=None,
    excluded_target_globs=None,
):
    excluded_target_globs = excluded_target_globs or []
    for repository_rel_path in repositories:
        if any(
            fnmatch.fnmatch(repository_rel_path, excluded_target_glob)
            for excluded_target_glob in excluded_target_globs
        ):
            continue
        for branch in origin_repo.branches():
            # ensures that git log will work
            client_repo.checkout_branch(branch)
            start_commit = None
            if start_head_shas is not None:
                start_commit = start_head_shas[repository_rel_path].get(branch)
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


def clone_repositories(
    origin_auth_repo,
    clients_dir,
    expected_repo_type=UpdateType.EITHER,
    excluded_target_globs=None):

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


def update_and_check_commit_shas(
    operation,
    client_repos,
    origin_auth_repo,
    clients_dir,
    expected_repo_type=UpdateType.EITHER,
    auth_repo_name_exists=True,
    excluded_target_globs=None,
):
    start_head_shas = _get_head_commit_shas(client_repos)
    clients_auth_repo_path = clients_dir / origin_auth_repo.name
    clients_auth_repo = GitRepository(path=clients_auth_repo_path)

    config = RepositoryConfig(
        operation=operation,
        url=str(origin_auth_repo.path),
        update_from_filesystem=True,
        path=str(clients_auth_repo_path) if auth_repo_name_exists else None,
        library_dir=str(clients_dir),
        expected_repo_type=expected_repo_type,
        excluded_target_globs=excluded_target_globs,
    )

    with freeze_time(_get_valid_update_time(origin_auth_repo.path)):
        if operation == OperationType.CLONE:
            clone_repository(config)
        else:
            update_repository(config)

    target_repositories = load_target_repositories(
        origin_auth_repo, clients_dir, excluded_target_globs
    )

    check_if_commits_match(
        target_repositories,
        origin_auth_repo,
        clients_auth_repo,
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
