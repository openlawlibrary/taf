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
and not updating snaphost) - test-updater-just-targets-updated. The update is expected to fail.

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

from tuf.ngclient._internal import trusted_metadata_set
from taf.auth_repo import AuthenticationRepository
from taf.exceptions import UpdateFailedError
from taf.git import GitRepository
from taf.updater.updater import update_repository, UpdateType
from taf.utils import on_rm_error

from taf.log import disable_console_logging, disable_file_logging
from .conftest import original_tuf_trusted_metadata_set

AUTH_REPO_REL_PATH = "organization/auth_repo"
TARGET_REPO_REL_PATH = "namespace/TargetRepo1"
TARGET1_SHA_MISMATCH = "Mismatch between target commits specified in authentication repository and target repository namespace/TargetRepo1"
TARGET2_SHA_MISMATCH = "Mismatch between target commits specified in authentication repository and target repository namespace/TargetRepo2"
TARGETS_MISMATCH_ANY = "Mismatch between target commits specified in authentication repository and target repository"
NO_WORKING_MIRRORS = (
    f"Validation of authentication repository {AUTH_REPO_REL_PATH} failed at revision"
)
NO_REPOSITORY_INFO_JSON = "Error during info.json parse. When specifying --clients-library-dir check if info.json metadata exists in targets/protected or provide full path to auth repo"
ROOT_EXPIRED = "Final root.json is expired"
REPLAYED_METADATA = "New timestamp version 3 must be >= 4"
METADATA_FIELD_MISSING = "New snapshot is missing info for 'root.json'"
IS_A_TEST_REPO = f"Repository {AUTH_REPO_REL_PATH} is a test repository."
NOT_A_TEST_REPO = f"Repository {AUTH_REPO_REL_PATH} is not a test repository."
LAST_VALIDATED_COMMIT_MISMATCH = "Saved last validated commit {} of repository {} does not match the current head commit {}"
UNCOMMITTED_TARGET_CHANGES = (
    f"Repository {TARGET_REPO_REL_PATH} should contain only committed changes."
)

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


@pytest.mark.parametrize(
    "test_name, test_repo, auth_repo_name_exists",
    [
        ("test-updater-valid", UpdateType.OFFICIAL, True),
        ("test-updater-valid", UpdateType.OFFICIAL, False),
        ("test-updater-valid-with-updated-expiration-dates", UpdateType.OFFICIAL, True),
        ("test-updater-allow-unauthenticated-commits", UpdateType.OFFICIAL, True),
        ("test-updater-test-repo", UpdateType.TEST, True),
        ("test-updater-multiple-branches", UpdateType.OFFICIAL, True),
        ("test-updater-delegated-roles", UpdateType.OFFICIAL, True),
        ("test-updater-updated-root", UpdateType.OFFICIAL, True),
        ("test-updater-updated-root-old-snapshot", UpdateType.OFFICIAL, True),
        ("test-updater-updated-root-version-skipped", UpdateType.OFFICIAL, True),
        ("test-updater-updated-root-version-skipped", UpdateType.OFFICIAL, True),
        ("test-updater-expired-metadata", UpdateType.OFFICIAL, True),
    ],
)
def test_valid_update_no_client_repo(
    test_name,
    test_repo,
    auth_repo_name_exists,
    updater_repositories,
    origin_dir,
    client_dir,
):
    repositories = updater_repositories[test_name]
    origin_dir = origin_dir / test_name
    _update_and_check_commit_shas(
        None, repositories, origin_dir, client_dir, test_repo, auth_repo_name_exists
    )


def test_excluded_targets_update_no_client_repo(
    updater_repositories,
    origin_dir,
    client_dir,
):
    repositories = updater_repositories["test-updater-valid"]
    origin_dir = origin_dir / "test-updater-valid"
    excluded_target_globs = ["*/TargetRepo1"]
    _update_and_check_commit_shas(
        None,
        repositories,
        origin_dir,
        client_dir,
        UpdateType.OFFICIAL,
        True,
        excluded_target_globs,
    )
    for repository_rel_path in repositories:
        for excluded_target_glob in excluded_target_globs:
            if fnmatch.fnmatch(repository_rel_path, excluded_target_glob):
                assert not Path(client_dir, repository_rel_path).is_dir()
                break


@pytest.mark.parametrize(
    "test_name, test_repo",
    [
        ("test-updater-valid", UpdateType.OFFICIAL),
        ("test-updater-allow-unauthenticated-commits", UpdateType.OFFICIAL),
        ("test-updater-multiple-branches", UpdateType.OFFICIAL),
        ("test-updater-delegated-roles", UpdateType.OFFICIAL),
    ],
)
def test_valid_update_no_auth_repo_one_target_repo_exists(
    test_name, test_repo, updater_repositories, origin_dir, client_dir
):
    repositories = updater_repositories[test_name]
    origin_dir = origin_dir / test_name
    _clone_client_repo(TARGET_REPO_REL_PATH, origin_dir, client_dir)
    _update_and_check_commit_shas(None, repositories, origin_dir, client_dir, test_repo)


@pytest.mark.parametrize(
    "test_name, num_of_commits_to_revert",
    [
        ("test-updater-valid", 3),
        ("test-updater-allow-unauthenticated-commits", 1),
        ("test-updater-multiple-branches", 5),
        ("test-updater-delegated-roles", 1),
        ("test-updater-updated-root", 1),
        ("test-updater-updated-root-old-snapshot", 1),
        ("test-updater-updated-root-version-skipped", 1),
    ],
)
def test_valid_update_existing_client_repos(
    test_name, num_of_commits_to_revert, updater_repositories, origin_dir, client_dir
):
    # clone the origin repositories
    # revert them to an older commit
    repositories = updater_repositories[test_name]
    origin_dir = origin_dir / test_name
    client_repos = _clone_and_revert_client_repositories(
        repositories, origin_dir, client_dir, num_of_commits_to_revert
    )
    # create valid last validated commit file
    _create_last_validated_commit(
        client_dir, client_repos[AUTH_REPO_REL_PATH].head_commit_sha()
    )
    _update_and_check_commit_shas(client_repos, repositories, origin_dir, client_dir)


@pytest.mark.parametrize(
    "test_name, test_repo",
    [
        ("test-updater-valid", UpdateType.OFFICIAL),
        ("test-updater-allow-unauthenticated-commits", UpdateType.OFFICIAL),
        ("test-updater-test-repo", UpdateType.TEST),
        ("test-updater-multiple-branches", UpdateType.OFFICIAL),
        ("test-updater-delegated-roles", UpdateType.OFFICIAL),
    ],
)
def test_no_update_necessary(
    test_name, test_repo, updater_repositories, origin_dir, client_dir
):
    # clone the origin repositories
    # revert them to an older commit
    repositories = updater_repositories[test_name]
    origin_dir = origin_dir / test_name
    client_repos = _clone_client_repositories(repositories, origin_dir, client_dir)
    # create valid last validated commit file
    _create_last_validated_commit(
        client_dir, client_repos[AUTH_REPO_REL_PATH].head_commit_sha()
    )
    _update_and_check_commit_shas(
        client_repos, repositories, origin_dir, client_dir, test_repo
    )


@pytest.mark.parametrize(
    "test_name, expected_error, auth_repo_name_exists",
    [
        ("test-updater-invalid-target-sha", TARGET1_SHA_MISMATCH, True),
        ("test-updater-additional-target-commit", TARGET1_SHA_MISMATCH, True),
        ("test-updater-missing-target-commit", TARGET1_SHA_MISMATCH, True),
        ("test-updater-wrong-key", NO_WORKING_MIRRORS, True),
        ("test-updater-invalid-version-number", REPLAYED_METADATA, True),
        ("test-updater-delegated-roles-wrong-sha", TARGET2_SHA_MISMATCH, True),
        ("test-updater-updated-root-n-root-missing", NO_WORKING_MIRRORS, True),
        ("test-updater-updated-root-invalid-metadata", NO_WORKING_MIRRORS, True),
        ("test-updater-info-missing", NO_REPOSITORY_INFO_JSON, False),
        (
            "test-updater-invalid-snapshot-meta-field-missing",
            METADATA_FIELD_MISSING,
            False,
        ),
    ],
)
def test_updater_invalid_update(
    test_name, expected_error, auth_repo_name_exists, updater_repositories, client_dir
):
    repositories = updater_repositories[test_name]
    clients_auth_repo_path = client_dir / AUTH_REPO_REL_PATH

    _update_invalid_repos_and_check_if_repos_exist(
        client_dir,
        repositories,
        expected_error,
        auth_repo_name_exists=auth_repo_name_exists,
    )
    # make sure that the last validated commit does not exist
    _check_if_last_validated_commit_exists(clients_auth_repo_path)


@pytest.mark.parametrize(
    "test_name, expected_error",
    [
        ("test-updater-invalid-target-sha", TARGET1_SHA_MISMATCH),
        ("test-updater-missing-target-commit", TARGET1_SHA_MISMATCH),
    ],
)
def test_valid_update_no_auth_repo_one_invalid_target_repo_exists(
    test_name, expected_error, updater_repositories, client_dir, origin_dir
):
    repositories = updater_repositories[test_name]
    clients_auth_repo_path = client_dir / AUTH_REPO_REL_PATH
    origin_dir = origin_dir / test_name
    _clone_client_repo(TARGET_REPO_REL_PATH, origin_dir, client_dir)
    _update_invalid_repos_and_check_if_repos_exist(
        client_dir, repositories, expected_error
    )
    # make sure that the last validated commit does not exist
    _check_if_last_validated_commit_exists(clients_auth_repo_path)


def test_updater_expired_metadata(updater_repositories, origin_dir, client_dir):
    # tuf patch state is shared between tests
    # so we manually revert to original tuf implementation
    trusted_metadata_set.TrustedMetadataSet = original_tuf_trusted_metadata_set

    # without using freeze_time, we expect to get metadata expired error
    repositories = updater_repositories["test-updater-expired-metadata"]
    clients_auth_repo_path = client_dir / AUTH_REPO_REL_PATH
    _update_invalid_repos_and_check_if_repos_exist(
        client_dir, repositories, ROOT_EXPIRED, set_time=False, strict=True
    )
    # make sure that the last validated commit does not exist
    _check_if_last_validated_commit_exists(clients_auth_repo_path)


@pytest.mark.parametrize(
    "test_name, num_of_commits_to_revert, expected_error",
    [
        ("test-updater-invalid-target-sha", 1, TARGET1_SHA_MISMATCH),
        ("test-updater-delegated-roles-wrong-sha", 4, TARGET2_SHA_MISMATCH),
    ],
)
def test_updater_invalid_target_sha_existing_client_repos(
    test_name,
    num_of_commits_to_revert,
    expected_error,
    updater_repositories,
    origin_dir,
    client_dir,
):
    repositories = updater_repositories[test_name]
    clients_auth_repo_path = client_dir / AUTH_REPO_REL_PATH
    origin_dir = origin_dir / test_name
    client_repos = _clone_and_revert_client_repositories(
        repositories, origin_dir, client_dir, num_of_commits_to_revert
    )
    _create_last_validated_commit(
        client_dir, client_repos[AUTH_REPO_REL_PATH].head_commit_sha()
    )
    _update_invalid_repos_and_check_if_remained_same(
        client_repos, client_dir, repositories, expected_error
    )
    _check_last_validated_commit(clients_auth_repo_path)


def test_no_target_repositories(updater_repositories, origin_dir, client_dir):
    repositories = updater_repositories["test-updater-valid"]
    origin_dir = origin_dir / "test-updater-valid"
    client_auth_repo = _clone_client_repo(AUTH_REPO_REL_PATH, origin_dir, client_dir)
    _create_last_validated_commit(client_dir, client_auth_repo.head_commit_sha())
    client_repos = {AUTH_REPO_REL_PATH: client_auth_repo}
    _update_invalid_repos_and_check_if_remained_same(
        client_repos, client_dir, repositories, TARGETS_MISMATCH_ANY
    )
    # make sure that the target repositories still do not exist
    for repository_rel_path in repositories:
        if repository_rel_path != AUTH_REPO_REL_PATH:
            client_repo_path = client_dir / repository_rel_path
            assert client_repo_path.exists() is False


def test_no_last_validated_commit(updater_repositories, origin_dir, client_dir):
    # clone the origin repositories
    # revert them to an older commit
    repositories = updater_repositories["test-updater-valid"]
    origin_dir = origin_dir / "test-updater-valid"
    client_repos = _clone_and_revert_client_repositories(
        repositories, origin_dir, client_dir, 3
    )
    # update without setting the last validated commit
    # update should start from the beginning and be successful
    _update_and_check_commit_shas(client_repos, repositories, origin_dir, client_dir)


def test_older_last_validated_commit(updater_repositories, origin_dir, client_dir):
    # clone the origin repositories
    # revert them to an older commit
    repositories = updater_repositories["test-updater-valid"]
    origin_dir = origin_dir / "test-updater-valid"
    client_repos = _clone_and_revert_client_repositories(
        repositories, origin_dir, client_dir, 3
    )
    all_commits = client_repos[AUTH_REPO_REL_PATH].all_commits_on_branch()
    first_commit = all_commits[0]

    _create_last_validated_commit(client_dir, first_commit)
    # try to update without setting the last validated commit
    _update_and_check_commit_shas(client_repos, repositories, origin_dir, client_dir)


def test_update_test_repo_no_flag(updater_repositories, origin_dir, client_dir):
    repositories = updater_repositories["test-updater-test-repo"]
    origin_dir = origin_dir / "test-updater-test-repo"
    # try to update a test repo, set update type to official
    _update_invalid_repos_and_check_if_repos_exist(
        client_dir, repositories, IS_A_TEST_REPO, UpdateType.OFFICIAL
    )


def test_update_repo_wrong_flag(updater_repositories, origin_dir, client_dir):
    repositories = updater_repositories["test-updater-valid"]
    origin_dir = origin_dir / "test-updater-valid"
    # try to update without setting the last validated commit
    _update_invalid_repos_and_check_if_repos_exist(
        client_dir, repositories, NOT_A_TEST_REPO, UpdateType.TEST
    )


def test_update_repo_target_in_indeterminate_state(
    updater_repositories, origin_dir, client_dir
):
    repositories = updater_repositories[
        "test-updater-target-repository-has-indeterminate-state"
    ]
    origin_dir = origin_dir / "test-updater-target-repository-has-indeterminate-state"

    targets_repo_path = client_dir / TARGET_REPO_REL_PATH

    _update_and_check_commit_shas(
        None, repositories, origin_dir, client_dir, UpdateType.OFFICIAL
    )
    # Create an `index.lock` file, indicating that an incomplete git operation took place
    # index.lock is created by git when a git operation is interrupted.
    index_lock = Path(targets_repo_path, ".git", "index.lock")
    index_lock.touch()

    _update_invalid_repos_and_check_if_repos_exist(
        client_dir, repositories, UNCOMMITTED_TARGET_CHANGES
    )


def _check_last_validated_commit(clients_auth_repo_path):
    # check if last validated commit is created and the saved commit is correct
    client_auth_repo = AuthenticationRepository(path=clients_auth_repo_path)
    head_sha = client_auth_repo.head_commit_sha()
    last_validated_commit = client_auth_repo.last_validated_commit
    assert head_sha == last_validated_commit


def _check_if_last_validated_commit_exists(clients_auth_repo_path):
    client_auth_repo = AuthenticationRepository(path=clients_auth_repo_path)
    last_validated_commit = client_auth_repo.last_validated_commit
    assert last_validated_commit is None


def _check_if_commits_match(
    repositories,
    origin_dir,
    client_dir,
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
        origin_repo = GitRepository(origin_dir, repository_rel_path)
        client_repo = GitRepository(client_dir, repository_rel_path)
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

        for branch in client_repo.branches():
            if branch not in branches_commits:
                client_repo.delete_local_branch(branch)

        client_repos[repository_rel_path] = client_repo

    return client_repos


def _clone_client_repo(
    repository_rel_path, origin_dir, client_dir, repo_class=GitRepository
):
    origin_repo_path = str(origin_dir / repository_rel_path)
    client_repo = repo_class(client_dir, repository_rel_path, urls=[origin_repo_path])
    client_repo.clone()
    return client_repo


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


def _get_valid_update_time(origin_auth_repo_path):
    # read timestamp.json expiration date
    timestamp_path = Path(origin_auth_repo_path, "metadata", "timestamp.json")
    timestamp_data = json.loads(timestamp_path.read_text())
    expires = timestamp_data["signed"]["expires"]
    return datetime.strptime(expires, "%Y-%m-%dT%H:%M:%SZ").date().strftime("%Y-%m-%d")


def _update_and_check_commit_shas(
    client_repos,
    repositories,
    origin_dir,
    client_dir,
    expected_repo_type=UpdateType.EITHER,
    auth_repo_name_exists=True,
    excluded_target_globs=None,
):
    start_head_shas = _get_head_commit_shas(client_repos)
    clients_auth_repo_path = client_dir / AUTH_REPO_REL_PATH
    origin_auth_repo_path = repositories[AUTH_REPO_REL_PATH]
    with freeze_time(_get_valid_update_time(origin_auth_repo_path)):
        update_repository(
            str(origin_auth_repo_path),
            str(clients_auth_repo_path) if auth_repo_name_exists else None,
            str(client_dir),
            "master",
            True,
            expected_repo_type=expected_repo_type,
            excluded_target_globs=excluded_target_globs,
        )
    _check_if_commits_match(
        repositories, origin_dir, client_dir, start_head_shas, excluded_target_globs
    )
    if not excluded_target_globs:
        _check_last_validated_commit(clients_auth_repo_path)


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

    with freeze_time(_get_valid_update_time(origin_auth_repo_path)):
        with pytest.raises(UpdateFailedError, match=expected_error):
            update_repository(
                str(origin_auth_repo_path),
                str(clients_auth_repo_path),
                str(client_dir),
                "master",
                True,
                expected_repo_type=expected_repo_type,
            )

    # all repositories should still have the same head commit
    for repo_path, repo in client_repos.items():
        for branch in repo.branches():
            start_commit = start_head_shas[repo_path].get(branch)
            current_head = repo.top_commit_of_branch(branch)
            assert current_head == start_commit


def _update_invalid_repos_and_check_if_repos_exist(
    client_dir,
    repositories,
    expected_error,
    expected_repo_type=UpdateType.EITHER,
    set_time=True,
    auth_repo_name_exists=True,
    strict=False,
):

    clients_auth_repo_path = client_dir / AUTH_REPO_REL_PATH
    origin_auth_repo_path = repositories[AUTH_REPO_REL_PATH]
    repositories_which_existed = [
        str(client_dir / repository_rel_path)
        for repository_rel_path in repositories
        if (client_dir / repository_rel_path).exists()
    ]

    def _update_expect_error(client_dir, expected_repo_type):
        with pytest.raises(UpdateFailedError, match=expected_error):
            update_repository(
                str(origin_auth_repo_path),
                str(clients_auth_repo_path) if auth_repo_name_exists else None,
                str(client_dir),
                "master",
                True,
                expected_repo_type=expected_repo_type,
                strict=strict,
            ),

    if set_time:
        with freeze_time(_get_valid_update_time(origin_auth_repo_path)):
            _update_expect_error(client_dir, expected_repo_type)
    else:
        _update_expect_error(client_dir, expected_repo_type)

    # the client repositories should not exits
    for repository_rel_path in repositories:
        path = client_dir / repository_rel_path
        if str(path) in repositories_which_existed:
            assert path.exists()
        else:
            assert not path.exists()
