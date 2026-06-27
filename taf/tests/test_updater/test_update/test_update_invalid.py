from taf.models.types import Commitish
import pytest
from taf.auth_repo import AuthenticationRepository
from taf.tests.test_updater.conftest import (
    DEFAULT_BRANCH_NOT_FOUND_PATTERN,
    INVALID_KEYS_PATTERN,
    LVC_NOT_IN_REMOTE_PATTERN,
    TARGET_MISSING_BRANCH_PATTERN,
    TARGET_MISSMATCH_PATTERN,
    UNCOMMITTED_CHANGES,
    OLD_LVC_FORMAT_ERROR_PATTERN,
    SetupManager,
    add_unauthenticated_commits_to_all_target_repos,
    add_valid_target_commits,
    create_file_without_committing,
    delete_target_branch,
    set_last_validated_commit_of_auth_repo,
    switch_target_branch_and_sign,
    update_expiration_dates,
    update_timestamp_metadata_invalid_signature,
    replace_with_old_last_validated_commit_format,
)
from taf.tests.test_updater.update_utils import (
    check_if_last_validated_commit_exists,
    clone_repositories,
    update_invalid_repos_and_check_if_repos_exist,
)
from taf.updater.types.update import OperationType

from taf.git import GitRepository


@pytest.mark.parametrize(
    "origin_auth_repo",
    [
        {
            "targets_config": [{"name": "target1"}, {"name": "target2"}],
        },
    ],
    indirect=True,
)
def test_update_invalid_target_repositories_contain_unsigned_commits(
    origin_auth_repo, client_dir
):

    clone_repositories(
        origin_auth_repo,
        client_dir,
    )

    setup_manager = SetupManager(origin_auth_repo)
    setup_manager.add_task(add_valid_target_commits)
    setup_manager.add_task(add_unauthenticated_commits_to_all_target_repos)
    setup_manager.add_task(add_valid_target_commits)
    setup_manager.execute_tasks()

    update_invalid_repos_and_check_if_repos_exist(
        OperationType.UPDATE,
        origin_auth_repo,
        client_dir,
        TARGET_MISSMATCH_PATTERN,
        True,
    )


@pytest.mark.parametrize(
    "origin_auth_repo",
    [
        {
            "targets_config": [{"name": "target1"}, {"name": "target2"}],
        },
    ],
    indirect=True,
)
def test_update_with_uncommitted_target_changes_and_upstream_updates_fails(
    origin_auth_repo, client_dir
):
    clone_repositories(
        origin_auth_repo,
        client_dir,
    )

    create_file_without_committing(origin_auth_repo, client_dir)

    setup_manager = SetupManager(origin_auth_repo)
    setup_manager.add_task(add_valid_target_commits)
    setup_manager.execute_tasks()

    update_invalid_repos_and_check_if_repos_exist(
        OperationType.UPDATE,
        origin_auth_repo,
        client_dir,
        UNCOMMITTED_CHANGES,
        True,
    )


@pytest.mark.parametrize(
    "origin_auth_repo",
    [
        {
            "targets_config": [{"name": "target1"}, {"name": "target2"}],
        },
    ],
    indirect=True,
)
def test_update_with_invalid_last_validated_commit(origin_auth_repo, client_dir):
    clone_repositories(origin_auth_repo, client_dir)

    invalid_commit_sha = Commitish.from_hash("66d7f48e972f9fa25196523f469227dfcd85c994")
    client_auth_repo = AuthenticationRepository(client_dir, origin_auth_repo.name)
    clients_setup_manager = SetupManager(client_auth_repo)
    clients_setup_manager.add_task(
        set_last_validated_commit_of_auth_repo, kwargs={"commit": invalid_commit_sha}
    )
    clients_setup_manager.execute_tasks()

    update_invalid_repos_and_check_if_repos_exist(
        OperationType.UPDATE,
        origin_auth_repo,
        client_dir,
        LVC_NOT_IN_REMOTE_PATTERN,
        True,
    )


@pytest.mark.parametrize(
    "origin_auth_repo",
    [
        {
            "targets_config": [{"name": "target1"}, {"name": "target2"}],
        }
    ],
    indirect=True,
)
def test_update_invalid_target_invalid_singature(origin_auth_repo, client_dir):

    clone_repositories(origin_auth_repo, client_dir)

    setup_manager = SetupManager(origin_auth_repo)
    setup_manager.add_task(update_timestamp_metadata_invalid_signature)
    setup_manager.add_task(update_expiration_dates)
    setup_manager.execute_tasks()

    update_invalid_repos_and_check_if_repos_exist(
        OperationType.UPDATE,
        origin_auth_repo,
        client_dir,
        INVALID_KEYS_PATTERN,
        True,
    )
    client_auth_repo = AuthenticationRepository(client_dir, origin_auth_repo.name)
    # make sure that the last validated commit does not exist
    check_if_last_validated_commit_exists(client_auth_repo, True)


@pytest.mark.parametrize(
    "origin_auth_repo",
    [
        {
            "targets_config": [{"name": "target1"}, {"name": "target2"}],
        },
    ],
    indirect=True,
)
def test_update_when_old_last_validated_commit(origin_auth_repo, client_dir):
    clone_repositories(
        origin_auth_repo,
        client_dir,
    )

    setup_manager = SetupManager(origin_auth_repo)
    setup_manager.add_task(add_valid_target_commits)
    setup_manager.execute_tasks()

    client_auth_repo = AuthenticationRepository(client_dir, origin_auth_repo.name)
    client_setup_manager = SetupManager(client_auth_repo)
    client_setup_manager.add_task(replace_with_old_last_validated_commit_format)
    client_setup_manager.execute_tasks()

    update_invalid_repos_and_check_if_repos_exist(
        OperationType.UPDATE,
        origin_auth_repo,
        client_dir,
        OLD_LVC_FORMAT_ERROR_PATTERN,
        True,
    )


@pytest.mark.parametrize(
    "origin_auth_repo",
    [
        {
            "targets_config": [{"name": "target1"}, {"name": "target2"}],
        },
    ],
    indirect=True,
)
def test_update_fails_when_target_repo_missing_referenced_branch(
    origin_auth_repo, client_dir
):
    """The auth repo's target metadata pins target1 at a commit on a branch that
    is not present in the target repository. The updater must fail with a clear
    error naming the target repo and the missing branch, not an IndexError/KeyError."""
    clone_repositories(origin_auth_repo, client_dir)

    missing_branch = "missing-branch"

    setup_manager = SetupManager(origin_auth_repo)
    # record a commit on `missing_branch` of target1 in the auth metadata
    setup_manager.add_task(
        switch_target_branch_and_sign,
        kwargs={"target_name": "target1", "branch_name": missing_branch},
    )
    # then remove that branch from the target repo so the auth repo references
    # a branch the target repo no longer contains
    setup_manager.add_task(
        delete_target_branch,
        kwargs={"target_name": "target1", "branch_name": missing_branch},
    )
    setup_manager.execute_tasks()

    update_invalid_repos_and_check_if_repos_exist(
        OperationType.UPDATE,
        origin_auth_repo,
        client_dir,
        TARGET_MISSING_BRANCH_PATTERN,
        True,
    )


@pytest.mark.parametrize(
    "origin_auth_repo",
    [
        {
            "targets_config": [{"name": "target1"}, {"name": "target2"}],
        },
    ],
    indirect=True,
)
def test_update_fails_when_default_branch_not_in_local_repo(
    origin_auth_repo, client_dir, monkeypatch
):
    clone_repositories(origin_auth_repo, client_dir)

    monkeypatch.setattr(
        GitRepository,
        "get_default_branch",
        lambda self, url=None: "non-existent-branch",
    )

    update_invalid_repos_and_check_if_repos_exist(
        OperationType.UPDATE,
        origin_auth_repo,
        client_dir,
        DEFAULT_BRANCH_NOT_FOUND_PATTERN,
        True,
    )
