"""
This module includes tests for the taf updater. The basic idea behind the tests is the following:
1. For each situation we want to test, there is a set of target repositories and an authentication repository.
For example, repositories where everything is completely valid, repositories where there is a mismatch between
a target repository's commit and the corresponding target commit sha in the auth repo etc.
These repositories are placed in tests/data/repos/test-updater directory and are copied to the origin directory
before any of the tests are executed. The repositories in the origin directory are used as remotes.
As a future improvements, we could reduce the number of repositories by adding/removing commits from tests.
2. We test update when no client repositories exist and when they do exist, but are not up to date.
When testing the second case, we clone the repositories and then revert them. We only modify client's repositories.
3. When everything is set up, update is called. Afterwards:
  1) If the update is expected to be successful, it is checked if pulled commits match commits of the remote
   repositories and if last_successful commit was created.
  2) If the update is expected to be unsuccessful, it is checked if the client's repositories remained the same
  (if they existed) or if they do not exist (in case they didn't exist in the first place) and if the
  error message is as expected.
4. Client repositories are deleted after every test to make sure that the execution of a previous test does
not impact the following ones.

These states of repositories are tested:
1. The authentication and target repositories are valid and all of the commits match - test-updater-valid. This
set of repositories is also used to test if the updater works in case when there is no need to perform the update,
and if the update fails if there are no client target repositories, but the auth repo exists.
2. There are additional commits in target repos (commits which are not accounted for by the auth repo) -
test-updater-additional-target-commit The update is performed until the last commit that can be validated.
Updated does not raise an error (a warning is logged).
3. The authentication and target repositories are valid and all of the commits match, but there are also auth
repo commits where only metadata files were updated (e.g. timestamp expiration date was changed) -
test-updater-valid-with-updated-expiration-dates. The update should be successful.
4. There are more commits noted in auth repo's target files than target repositories' commits
test-updater-missing-target-commit. The update is expected to fail.
5. The commits of the target repositories do not match commits noted in the auth repo - test-updater-invalid-target-sha.
The update is expected to fail.
6. A metadata file's signature is not valid - test-updater-wrong-key. The update is expected to fail.
7. A metadata file's expiration date is not valid - test-updater-invalid-expiration-date.
The update is expected to fail.
8. A metadata file's version number is not valid (this test case was created by swapping commits using
git rebase) - test-updater-invalid-version-number. The update is expected to fail.
9. A metadata file which should have remained the same changed (this test case was created by updating targets
and not updating snapshot) - test-updater-just-targets-updated. The update is expected to fail.

On top of that, it is tested that update fails if last_validated_commit does not exist, while the client's repository
does and if it does exist, but the stored commit does not match the client repository's head commit.
"""

import os
import shutil
import fnmatch
from pathlib import Path
from collections import defaultdict
import json

import pytest
from pytest import fixture
from freezegun import freeze_time
from datetime import datetime

import taf.settings as settings

from taf.tests.test_updater.update_utils import (
    _get_valid_update_time,
    check_if_commits_match,
    check_last_validated_commit,
    update_and_check_commit_shas,
)
from tuf.ngclient._internal import trusted_metadata_set
from taf.auth_repo import AuthenticationRepository
from taf.exceptions import UpdateFailedError
from taf.git import GitRepository
from taf.updater.updater import (
    RepositoryConfig,
    clone_repository,
    update_repository,
    UpdateType,
)
from taf.utils import on_rm_error

from taf.log import disable_console_logging, disable_file_logging

from taf.tests.test_updater.test_repo_update.conftest import (
    original_tuf_trusted_metadata_set,
)
from taf.updater.types.update import OperationType

AUTH_REPO_REL_PATH = "organization/auth_repo"
TARGET_REPO_REL_PATH = "namespace/TargetRepo1"


REPLAYED_METADATA = "New timestamp version 3 must be >= 4"
METADATA_FIELD_MISSING = "New snapshot is missing info for 'root.json'"
IS_A_TEST_REPO = f"Repository {AUTH_REPO_REL_PATH} is a test repository."
NOT_A_TEST_REPO = f"Repository {AUTH_REPO_REL_PATH} is not a test repository."


disable_console_logging()
disable_file_logging()


def setup_module(module):
    settings.update_from_filesystem = True


def teardown_module(module):
    settings.update_from_filesystem = False


@fixture(autouse=True)
def run_around_tests(client_dir):
    yield
    for root, dirs, _ in os.walk(str(client_dir)):
        for dir_name in dirs:
            shutil.rmtree(str(Path(root) / dir_name), onerror=on_rm_error)



# @pytest.mark.parametrize(
#     "test_name, num_of_commits_to_revert, expected_error",
#     [
#         ("test-updater-invalid-target-sha", 1, TARGET_MISSMATCH_PATTERN),
#         ("test-updater-delegated-roles-wrong-sha", 4, TARGET_MISSMATCH_PATTERN),
#     ],
# )
# def test_updater_invalid_target_sha_existing_client_repos(
#     test_name,
#     num_of_commits_to_revert,
#     expected_error,
#     updater_repositories,
#     origin_dir,
#     client_dir,
# ):
#     repositories = updater_repositories[test_name]
#     clients_auth_repo_path = client_dir / AUTH_REPO_REL_PATH
#     origin_dir = origin_dir / test_name
#     client_repos = _clone_and_revert_client_repositories(
#         repositories, origin_dir, client_dir, num_of_commits_to_revert
#     )
#     _create_last_validated_commit(
#         client_dir, client_repos[AUTH_REPO_REL_PATH].head_commit_sha()
#     )
#     _update_invalid_repos_and_check_if_remained_same(
#         client_repos, client_dir, repositories, expected_error
#     )
#     _check_last_validated_commit(clients_auth_repo_path)


# def test_no_target_repositories(updater_repositories, origin_dir, client_dir):
#     repositories = updater_repositories["test-updater-valid"]
#     origin_dir = origin_dir / "test-updater-valid"
#     client_auth_repo = _clone_client_repo(AUTH_REPO_REL_PATH, origin_dir, client_dir)
#     _create_last_validated_commit(client_dir, client_auth_repo.head_commit_sha())
#     update_and_check_commit_shas(
#         OperationType.UPDATE, None, repositories, origin_dir, client_dir, False
#     )


# def test_no_last_validated_commit(updater_repositories, origin_dir, client_dir):
#     # clone the origin repositories
#     # revert them to an older commit
#     repositories = updater_repositories["test-updater-valid"]
#     origin_dir = origin_dir / "test-updater-valid"
#     client_repos = _clone_and_revert_client_repositories(
#         repositories, origin_dir, client_dir, 3
#     )
#     # update without setting the last validated commit
#     # update should start from the beginning and be successful
#     update_and_check_commit_shas(
#         OperationType.UPDATE, client_repos, repositories, origin_dir, client_dir
#     )


# def test_older_last_validated_commit(updater_repositories, origin_dir, client_dir):
#     # clone the origin repositories
#     # revert them to an older commit
#     repositories = updater_repositories["test-updater-valid"]
#     origin_dir = origin_dir / "test-updater-valid"
#     client_repos = _clone_and_revert_client_repositories(
#         repositories, origin_dir, client_dir, 3
#     )
#     all_commits = client_repos[AUTH_REPO_REL_PATH].all_commits_on_branch()
#     first_commit = all_commits[0]

#     _create_last_validated_commit(client_dir, first_commit)
#     # try to update without setting the last validated commit
#     update_and_check_commit_shas(
#         OperationType.UPDATE, client_repos, repositories, origin_dir, client_dir
#     )



# def test_update_repo_target_in_indeterminate_state(
#     updater_repositories, origin_dir, client_dir
# ):
#     repositories = updater_repositories[
#         "test-updater-target-repository-has-indeterminate-state"
#     ]
#     origin_dir = origin_dir / "test-updater-target-repository-has-indeterminate-state"

#     targets_repo_path = client_dir / TARGET_REPO_REL_PATH

#     update_and_check_commit_shas(
#         OperationType.CLONE,
#         None,
#         repositories,
#         origin_dir,
#         client_dir,
#         UpdateType.OFFICIAL,
#     )
#     # Create an `index.lock` file, indicating that an incomplete git operation took place
#     # index.lock is created by git when a git operation is interrupted.
#     index_lock = Path(targets_repo_path, ".git", "index.lock")
#     index_lock.touch()

#     _update_invalid_repos_and_check_if_repos_exist(
#         OperationType.UPDATE, client_dir, repositories, NOT_CLEAN_PATTERN, True
#     )


# def test_update_repository_with_dependencies(
#     library_with_dependencies,
#     origin_dir,
#     client_dir,
# ):
#     _update_full_library(
#         OperationType.CLONE,
#         library_with_dependencies,
#         origin_dir,
#         client_dir,
#         expected_repo_type=UpdateType.EITHER,
#         auth_repo_name_exists=True,
#         excluded_target_globs=None,
#     )



def _clone_client_repositories(repositories, origin_dir, client_dir):
    client_repos = {}
    for repository_rel_path in repositories:
        client_repo = _clone_client_repo(repository_rel_path, origin_dir, client_dir)
        client_repos[repository_rel_path] = client_repo
    return client_repos


def _clone_and_revert_client_repositories(
    repositories, origin_dir, client_dir, num_of_commits
):
    client_repos = {}
    client_auth_repo = _clone_client_repo(
        AUTH_REPO_REL_PATH, origin_dir, client_dir, repo_class=AuthenticationRepository
    )
    client_auth_repo.reset_num_of_commits(num_of_commits, True)
    client_auth_repo.reset_remote_tracking_branch(client_auth_repo.default_branch)

    client_repos[AUTH_REPO_REL_PATH] = client_auth_repo
    client_auth_commits = client_auth_repo.all_commits_on_branch()

    def _get_commit_and_branch(target_name, auth_repo_commit):
        data = client_auth_repo.get_target(target_name, auth_repo_commit)
        if data is None:
            return None, None
        return data.get("commit"), data.get("branch", "master")

    for repository_rel_path in repositories:
        if repository_rel_path == AUTH_REPO_REL_PATH:
            continue

        client_repo = _clone_client_repo(repository_rel_path, origin_dir, client_dir)
        branches_commits = {}
        for auth_commit in client_auth_commits:
            commit, branch = _get_commit_and_branch(repository_rel_path, auth_commit)
            if branch is not None and commit is not None:
                branches_commits[branch] = commit

        if branch in branches_commits:
            client_repo.checkout_branch(branch)
            client_repo.reset_to_commit(commit, True)
            client_repo.reset_remote_tracking_branch(branch)

        for branch in client_repo.branches():
            if branch not in branches_commits:
                client_repo.delete_local_branch(branch)

        client_repos[repository_rel_path] = client_repo

    return client_repos


def _create_last_validated_commit(client_dir, client_auth_repo_head_sha):
    client_conf_repo = client_dir / "organization/_auth_repo"
    client_conf_repo.mkdir(parents=True, exist_ok=True)
    with open(str(client_conf_repo / "last_validated_commit"), "w") as f:
        f.write(client_auth_repo_head_sha)


def _get_head_commit_shas(client_repos):
    start_head_shas = defaultdict(dict)
    if client_repos is not None:
        for repo_rel_path, repo in client_repos.items():
            for branch in repo.branches():
                start_head_shas[repo_rel_path][branch] = repo.top_commit_of_branch(
                    branch
                )
    return start_head_shas


def _update_full_library(
    operation,
    library_dict,
    origin_dir,
    client_dir,
    expected_repo_type=UpdateType.EITHER,
    auth_repo_name_exists=True,
    excluded_target_globs=None,
):

    all_repositories = []
    for repo_info in library_dict.values():
        # Add the auth repository
        all_repositories.append(repo_info["auth_repo"])
        # Extend the list with all target repositories
        all_repositories.extend(repo_info["target_repos"])

    start_head_shas = defaultdict(dict)
    for repo in all_repositories:
        for branch in repo.branches():
            start_head_shas[repo.name][branch] = repo.top_commit_of_branch(branch)

    origin_root_repo = library_dict["root/auth"]["auth_repo"]
    clients_auth_repo_path = client_dir / "root/auth"
    # origin_auth_repo_path = repositories[AUTH_REPO_REL_PATH]

    config = RepositoryConfig(
        operation=operation,
        url=str(origin_root_repo.path),
        update_from_filesystem=True,
        path=str(clients_auth_repo_path) if auth_repo_name_exists else None,
        library_dir=str(client_dir),
        expected_repo_type=expected_repo_type,
        excluded_target_globs=excluded_target_globs,
    )

    with freeze_time(_get_valid_update_time(origin_root_repo.path)):
        if operation == OperationType.CLONE:
            clone_repository(config)
        else:
            update_repository(config)

    repositories = {}
    for auth_repo_name, repos in library_dict.items():
        repositories[auth_repo_name] = repos["auth_repo"]
        for target_repo in repos["target_repos"]:
            repositories[target_repo.name] = target_repo
        check_last_validated_commit(client_dir / repos["auth_repo"].name)
    check_if_commits_match(
        repositories, origin_dir, client_dir, start_head_shas, excluded_target_globs
    )


def _update_invalid_repos_and_check_if_remained_same(
    client_repos,
    client_dir,
    repositories,
    expected_error,
    expected_repo_type=UpdateType.EITHER,
):

    start_head_shas = _get_head_commit_shas(client_repos)
    clients_auth_repo_path = client_dir / AUTH_REPO_REL_PATH
    origin_auth_repo_path = repositories[AUTH_REPO_REL_PATH]

    config = RepositoryConfig(
        operation=OperationType.UPDATE,
        url=str(origin_auth_repo_path),
        update_from_filesystem=True,
        path=str(clients_auth_repo_path),
        library_dir=str(client_dir),
        expected_repo_type=expected_repo_type,
    )

    with freeze_time(_get_valid_update_time(origin_auth_repo_path)):
        with pytest.raises(UpdateFailedError, match=expected_error):
            update_repository(config)

    # all repositories should still have the same head commit
    for repo_path, repo in client_repos.items():
        for branch in repo.branches():
            start_commit = start_head_shas[repo_path].get(branch)
            current_head = repo.top_commit_of_branch(branch)
            assert current_head == start_commit

