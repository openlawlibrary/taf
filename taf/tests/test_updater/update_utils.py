import os
import shutil

from taf.models.types import Commitish
import pytest
from pathlib import Path
from freezegun import freeze_time
from collections import defaultdict
from datetime import datetime
import fnmatch
import json
from taf import repositoriesdb
from taf.auth_repo import AuthenticationRepository, Optional
from taf.git import GitRepository
from taf.exceptions import UpdateFailedError
from taf.updater.types.update import OperationType, UpdateType
from taf.updater.updater import UpdateConfig, clone_repository, update_repository


def check_last_validated_commit(
    clients_auth_repo_path, all_target_repositories=None, excluded_targets=None
):
    # check if last validated commit is created and the saved commit is correct
    client_auth_repo = AuthenticationRepository(path=clients_auth_repo_path)
    head_sha = client_auth_repo.head_commit()
    last_validated_data = client_auth_repo.last_validated_data
    assert last_validated_data[client_auth_repo.name] == head_sha.value
    if not excluded_targets:
        assert (
            client_auth_repo.last_validated_data[client_auth_repo.LAST_VALIDATED_KEY]
            == head_sha.value
        )

    if all_target_repositories and excluded_targets:
        for target_repo in all_target_repositories:
            if target_repo not in excluded_targets:
                assert last_validated_data[target_repo.name] == head_sha.value
            else:
                assert last_validated_data.get(target_repo.name) != head_sha.value


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
            # client_repo.checkout_branch(branch)
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
            client_auth_repo.top_commit_of_branch(client_auth_repo.default_branch).value
            == last_validated_commit
        )


def clone_full_library(
    library_dict,
    origin_dir,
    client_dir,
    expected_repo_type=UpdateType.EITHER,
    excluded_target_globs=None,
):
    origin_root_repo = library_dict["root/auth"]["auth_repo"]

    git_dir = os.path.join(origin_root_repo.path, ".git")
    if not os.path.exists(git_dir):
        # Log a warning and skip cloning this repository
        print(
            "Warning: Update of root/auth failed. One or more referenced authentication repositories could not be validated: "
            "Repository root/auth is missing .git directory."
        )
        return

    all_repositories = []
    for repo_info in library_dict.values():
        all_repositories.append(repo_info["auth_repo"])
        all_repositories.extend(repo_info["target_repos"])

    start_head_shas = defaultdict(dict)
    for repo in all_repositories:
        for branch in repo.branches():
            start_head_shas[repo.name][branch] = repo.top_commit_of_branch(branch)

    clone_repositories(
        origin_root_repo,
        client_dir,
        expected_repo_type=expected_repo_type,
    )

    repositories = {}
    for auth_repo_name, repos in library_dict.items():
        repositories[auth_repo_name] = repos["auth_repo"]
        for target_repo in repos["target_repos"]:
            repositories[target_repo.name] = target_repo
        check_last_validated_commit(client_dir / repos["auth_repo"].name)

    check_if_commits_match(
        repositories, origin_dir, start_head_shas, excluded_target_globs
    )


def count_subdirectories_in_directory(directory_path):
    """
    Counts the number of subdirectories in the given directory.

    Args:
        directory_path (str or Path): The path to the directory where subdirectories are to be counted.

    Returns:
        int: The number of subdirectories in the specified directory.
    """
    # Convert directory_path to Path object if it's not already one
    directory = (
        Path(directory_path) if not isinstance(directory_path, Path) else directory_path
    )

    # Count folders using a generator expression
    folder_count = sum(1 for item in directory.iterdir() if item.is_dir())

    return folder_count


def clone_repositories(
    origin_auth_repo,
    clients_dir,
    expected_repo_type=UpdateType.EITHER,
    excluded_target_globs=None,
):

    # there is a cleanup issue caused by a file being in use
    # delete before running the tests if exists
    client_test_root = clients_dir / origin_auth_repo.name.split("/")[0]
    if (client_test_root).is_dir():
        shutil.rmtree(client_test_root)
    config = UpdateConfig(
        operation=OperationType.CLONE,
        remote_url=str(origin_auth_repo.path),
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


def _get_head_commit_shas(client_repos, num_of_commits_to_remove=None):
    if num_of_commits_to_remove is None:
        num_of_commits_to_remove = {}

    start_head_shas = defaultdict(dict)
    if client_repos is not None:
        for repo_name, repo in client_repos.items():
            to_revert = num_of_commits_to_remove.get(repo_name, 0)
            for branch in repo.branches():
                if to_revert == 0:
                    start_head_shas[repo_name][branch] = repo.top_commit_of_branch(
                        branch
                    )
                else:
                    all_commits = repo.all_commits_on_branch(branch)
                    start_head_shas[repo_name][branch] = all_commits[-to_revert - 1]
    return start_head_shas


def load_target_repositories(
    auth_repo,
    library_dir=None,
    excluded_target_globs=None,
    commits=None,
    only_load_targets=False,
):
    if library_dir is None:
        library_dir = auth_repo.path.parent.parent

    repositoriesdb.clear_repositories_db()
    repositoriesdb.load_repositories(
        auth_repo,
        library_dir=library_dir,
        only_load_targets=only_load_targets,
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
    force=False,
    bare=False,
    no_upstream=False,
    skip_check_last_validated=False,
    num_of_commits_to_remove=None,
):
    client_repos = load_target_repositories(origin_auth_repo, clients_dir)
    client_repos = {
        repo_name: repo
        for repo_name, repo in client_repos.items()
        if repo.path.is_dir()
    }

    clients_auth_repo_path = clients_dir / origin_auth_repo.name
    clients_auth_repo = AuthenticationRepository(path=clients_auth_repo_path)
    if clients_auth_repo_path.is_dir():
        client_repos[clients_auth_repo.name] = clients_auth_repo
    start_head_shas = _get_head_commit_shas(client_repos, num_of_commits_to_remove)

    config = UpdateConfig(
        operation=operation,
        remote_url=str(origin_auth_repo.path),
        update_from_filesystem=True,
        path=str(clients_auth_repo_path) if auth_repo_name_exists else None,
        library_dir=str(clients_dir),
        expected_repo_type=expected_repo_type,
        excluded_target_globs=excluded_target_globs,
        bare=bare,
        force=force,
        no_upstream=no_upstream,
    )

    if operation == OperationType.CLONE:
        update_ret = clone_repository(config)
    else:
        update_ret = update_repository(config)

    origin_root_dir = origin_auth_repo.path.parent.parent
    check_if_commits_match(
        client_repos,
        origin_root_dir,
        start_head_shas,
        excluded_target_globs,
    )

    excluded_targets = []
    repositoriesdb.clear_repositories_db()
    all_target_repositories = load_target_repositories(origin_auth_repo, clients_dir)
    if excluded_target_globs:
        total_dirs_count = count_subdirectories_in_directory(
            clients_auth_repo_path.parent
        )
        for target_repo in all_target_repositories.values():
            target_skipped = False
            for excluded_target_glob in excluded_target_globs:
                if fnmatch.fnmatch(target_repo.name, excluded_target_glob):
                    excluded_targets.append(target_repo)
                    if (
                        operation == OperationType.CLONE
                        or target_repo in clients_auth_repo.last_validated_data
                    ):
                        assert not target_repo.path.is_dir()
                    else:
                        # already cloned, but excluded in this updated
                        assert target_repo.path.is_dir()
                    target_skipped = True
                    break
            if not target_skipped:
                assert target_repo.path.is_dir()

        assert len(excluded_targets) > 0
        # all target repositories + auth repo + auth repo conf dir - skipped repos
        if operation == OperationType.CLONE:
            assert total_dirs_count == len(all_target_repositories) + 2 - len(
                excluded_targets
            )

    if not skip_check_last_validated:
        check_last_validated_commit(
            clients_auth_repo_path, all_target_repositories.values(), excluded_targets
        )

    return update_ret


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
    no_upstream=False,
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

    config = UpdateConfig(
        operation=operation,
        remote_url=str(origin_auth_repo.path),
        update_from_filesystem=True,
        path=str(clients_auth_repo_path) if auth_repo_name_exists else None,
        library_dir=str(clients_dir),
        expected_repo_type=expected_repo_type,
        excluded_target_globs=excluded_target_globs,
        strict=strict,
        no_upstream=no_upstream,
    )

    def _update_expect_error():
        with pytest.raises(UpdateFailedError, match=expected_error):
            if operation == OperationType.CLONE:
                clone_repository(config)
            else:
                update_repository(config)

    _update_expect_error()

    if not expect_partial_update:
        # the client repositories should not exist
        for client_repository in client_repos.values():
            if client_repository.path in repositories_which_existed_paths:
                assert client_repository.path.exists()
            else:
                assert not client_repository.path.exists()


def verify_repos_exist(
    client_dir: Path,
    origin_auth_repo: AuthenticationRepository,
    excluded: Optional[list] = None,
):
    if excluded is None:
        excluded = []
    client_auth_repo = AuthenticationRepository(path=client_dir / origin_auth_repo.name)
    client_target_repos = load_target_repositories(
        client_auth_repo, library_dir=client_dir
    )
    for repo in client_target_repos.values():
        if repo.name.split("/")[-1] in excluded:
            assert not repo.is_git_repository
        else:
            assert repo.path.is_dir()


def verify_repo_empty(
    client_dir: Path, origin_auth_repo: AuthenticationRepository, target_name_part: str
):
    client_auth_repo = AuthenticationRepository(path=client_dir / origin_auth_repo.name)
    client_target_repos = load_target_repositories(
        client_auth_repo, library_dir=client_dir
    )
    for name, repo in client_target_repos.items():
        if target_name_part in name:
            assert not len(repo.all_commits_on_branch())


def verify_client_repos_state(
    client_dir: Path, origin_auth_repo: AuthenticationRepository
):
    """
    Verify that the client's repositories are in the correct state.
    This means that the target repositories in the client repo should be in sync with the origin repo,
    and the client's auth repo should be updated to the last validated commit.
    """
    client_auth_repo = AuthenticationRepository(path=client_dir / origin_auth_repo.name)
    client_target_repos = load_target_repositories(
        origin_auth_repo, library_dir=client_dir
    )

    # check if the target repositoies are in sync with the auth repo

    for repo_name, client_repo in client_target_repos.items():
        client_commit = client_repo.head_commit()

        # Extract commit SHA from the target file in the client repo
        target_commit_info = client_auth_repo.get_target(repo_name)
        target_commit_sha = Commitish.from_hash(
            target_commit_info.get("commit") if target_commit_info else None
        )

        # Assert that the top commits of target repositories are the same as the commit SHA specified in the corresponding target files
        assert (
            client_commit == target_commit_sha
        ), f"Target repo {repo_name} should have the same top commit as specified in the corresponding target file"


def verify_partial_auth_update(
    client_dir: Path, origin_auth_repo: AuthenticationRepository
):
    """
    Verify that the client's repositories are in the correct state following a partial update.
    This means that the top commits of the client's local target repositories are different
    from the top commits of the origin repositories, and they match the most recent valid
    commit as specified in the client's auth repo.
    """
    client_auth_repo = AuthenticationRepository(path=client_dir / origin_auth_repo.name)

    # Ensure the last validated commit exists in the client's auth repo
    check_last_validated_commit(client_auth_repo.path)

    client_head_sha = client_auth_repo.head_commit()
    assert client_head_sha != origin_auth_repo.head_commit()
    assert client_head_sha in origin_auth_repo.all_commits_on_branch()


def verify_partial_targets_update(
    client_dir: Path, origin_auth_repo: AuthenticationRepository
):

    client_auth_repo = AuthenticationRepository(path=client_dir / origin_auth_repo.name)

    client_target_repos = load_target_repositories(
        origin_auth_repo, library_dir=client_dir
    )
    for repo_name, client_repo in client_target_repos.items():
        client_commit = client_repo.head_commit()
        origin_commit = origin_auth_repo.head_commit()

        # Ensure the client repository commit is different from the origin repo commit
        assert (
            client_commit != origin_commit
        ), f"Target repo {repo_name} should not have the same top commit as the origin repo after a partial update"

        # Verify that the client's repo commit matches the expected commit SHA in the auth repo
        target = client_auth_repo.get_target(repo_name)

        # Use the get method to safely access the "commit" key
        expected_commit_sha = target.get("commit") if target else None

        expected_commit = Commitish.from_hash(expected_commit_sha)
        # Ensure expected_commit_sha is not None before proceeding
        assert (
            expected_commit is not None
        ), f"Commit SHA for {repo_name} is missing in the auth repo"

        assert (
            client_commit == expected_commit
        ), f"Target repo {repo_name} should have the same top commit as specified in the client's auth repo"


def update_and_validate_repositories(
    library_with_dependencies,
    origin_dir,
    client_dir,
    invalid_target_names=None,
    excluded_target_globs=None,
):
    if invalid_target_names is None:
        invalid_target_names = []

    all_repositories = []
    for repo_info in library_with_dependencies.values():
        all_repositories.append(repo_info["auth_repo"])
        all_repositories.extend(repo_info["target_repos"])

    start_head_shas = defaultdict(dict)
    for repo in all_repositories:
        for branch in repo.branches():
            start_head_shas[repo.name][branch] = repo.top_commit_of_branch(branch)

    origin_root_repo = library_with_dependencies["root/auth"]["auth_repo"]

    try:
        update_and_check_commit_shas(
            OperationType.UPDATE,
            origin_root_repo,
            client_dir,
            excluded_target_globs=excluded_target_globs,
        )
    except UpdateFailedError as e:
        if any(
            invalid_target_name in str(e)
            for invalid_target_name in invalid_target_names
        ):
            pass  # Skip the repositories that are invalid
        else:
            raise e

    def _check_if_invalid_repo_remain_same(repo_name):
        repo = next(repo for repo in all_repositories if repo.name == repo_name)
        for branch in start_head_shas[repo_name]:
            assert start_head_shas[repo_name][branch] == repo.top_commit_of_branch(
                branch
            )

    for auth_repo_name, repo_info in library_with_dependencies.items():
        auth_repo = repo_info["auth_repo"]
        for target_repo in repo_info["target_repos"]:
            if target_repo.name not in invalid_target_names:
                check_if_commits_match(
                    {auth_repo_name: auth_repo, target_repo.name: target_repo},
                    origin_dir,
                    start_head_shas,
                )
            else:
                _check_if_invalid_repo_remain_same(target_repo.name)

    for auth_repo_name, repo_info in library_with_dependencies.items():
        if repo_info["auth_repo"].name in invalid_target_names:
            _check_if_invalid_repo_remain_same(repo_info["auth_repo"].name)
