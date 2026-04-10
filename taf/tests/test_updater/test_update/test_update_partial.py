from pathlib import Path

import pytest
from taf.auth_repo import AuthenticationRepository
from taf.tests.test_updater.conftest import (
    SetupManager,
    add_valid_target_commits,
    set_head_commit,
    update_target_repo_without_committing,
)
from taf.tests.test_updater.update_utils import (
    UpdateType,
    clone_repositories,
    update_and_check_commit_shas,
    verify_excluded_lvc_entries,
    verify_repos_exist,
)
from taf.updater.types.update import OperationType


@pytest.mark.parametrize(
    "origin_auth_repo",
    [
        {
            "targets_config": [{"name": "target1"}, {"name": "target2"}],
        },
    ],
    indirect=True,
)
def test_update_partial_with_invalid_commits(origin_auth_repo, client_dir):
    clone_repositories(
        origin_auth_repo,
        client_dir,
    )
    client_auth_repo_path = client_dir / origin_auth_repo.name
    client_auth_repo = AuthenticationRepository(path=client_auth_repo_path)

    setup_manager = SetupManager(origin_auth_repo)
    setup_manager.add_task(add_valid_target_commits)
    setup_manager.execute_tasks()

    setup_manager.add_task(set_head_commit)

    setup_manager.add_task(add_valid_target_commits)
    setup_manager.execute_tasks()

    setup_manager = SetupManager(client_auth_repo)
    setup_manager.add_task(
        update_target_repo_without_committing, kwargs={"target_name": "target1"}
    )
    setup_manager.execute_tasks()

    update_and_check_commit_shas(
        OperationType.UPDATE,
        origin_auth_repo,
        client_dir,
        force=True,
    )


@pytest.mark.parametrize(
    "origin_auth_repo",
    [
        {
            "targets_config": [
                {"name": "target_same1"},
                {"name": "target_same2"},
                {"name": "target_different"},
            ],
        },
    ],
    indirect=True,
)
def test_update_when_clone_with_excluded_update_all(origin_auth_repo, client_dir):

    setup_manager = SetupManager(origin_auth_repo)
    setup_manager.add_task(add_valid_target_commits)
    setup_manager.execute_tasks()

    is_test_repo = origin_auth_repo.is_test_repo
    expected_repo_type = UpdateType.TEST if is_test_repo else UpdateType.OFFICIAL
    update_and_check_commit_shas(
        OperationType.CLONE,
        origin_auth_repo,
        client_dir,
        expected_repo_type=expected_repo_type,
        exclude_filter="'target_same' in repo['name']",
    )
    verify_excluded_lvc_entries(client_dir, origin_auth_repo, excluded=["target_same"])

    update_and_check_commit_shas(
        OperationType.UPDATE,
        origin_auth_repo,
        client_dir,
        expected_repo_type=expected_repo_type,
    )


@pytest.mark.parametrize(
    "origin_auth_repo",
    [
        {
            "targets_config": [
                {"name": "target_same1"},
                {"name": "target_same2"},
                {"name": "target_different"},
            ],
        },
    ],
    indirect=True,
)
def test_full_update_after_partial_clone(origin_auth_repo, client_dir):
    setup_manager = SetupManager(origin_auth_repo)
    setup_manager.add_task(add_valid_target_commits)
    setup_manager.add_task(add_valid_target_commits)
    setup_manager.execute_tasks()
    is_test_repo = origin_auth_repo.is_test_repo
    expected_repo_type = UpdateType.TEST if is_test_repo else UpdateType.OFFICIAL

    update_and_check_commit_shas(
        OperationType.CLONE,
        origin_auth_repo,
        client_dir,
        expected_repo_type=expected_repo_type,
        exclude_filter="'target_same' in repo['name']",
    )
    excluded = ["target_same1", "target_same2"]
    verify_repos_exist(client_dir, origin_auth_repo, excluded)
    verify_excluded_lvc_entries(client_dir, origin_auth_repo, excluded)
    # this update should be successful because we are skipping the invalid repo
    update_and_check_commit_shas(
        OperationType.UPDATE,
        origin_auth_repo,
        client_dir,
        no_upstream=False,
        expected_repo_type=expected_repo_type,
    )
    verify_repos_exist(client_dir, origin_auth_repo, excluded)
    verify_excluded_lvc_entries(client_dir, origin_auth_repo, excluded)


@pytest.mark.parametrize(
    "origin_auth_repo",
    [
        {
            "targets_config": [
                {"name": "target_same1"},
                {"name": "target_same2"},
                {"name": "target_different"},
            ],
        },
    ],
    indirect=True,
)
def test_update_after_partial_clone_with_deleted_lvc(origin_auth_repo, client_dir):
    """Clone with exclude_filter, delete last_validated_commit, then update."""
    setup_manager = SetupManager(origin_auth_repo)
    setup_manager.add_task(add_valid_target_commits)
    setup_manager.execute_tasks()

    is_test_repo = origin_auth_repo.is_test_repo
    expected_repo_type = UpdateType.TEST if is_test_repo else UpdateType.OFFICIAL

    update_and_check_commit_shas(
        OperationType.CLONE,
        origin_auth_repo,
        client_dir,
        expected_repo_type=expected_repo_type,
        exclude_filter="'target_same' in repo['name']",
    )

    excluded = ["target_same1", "target_same2"]
    verify_repos_exist(client_dir, origin_auth_repo, excluded)
    verify_excluded_lvc_entries(client_dir, origin_auth_repo, excluded)

    # Delete the last_validated_commit file
    client_auth_repo = AuthenticationRepository(path=client_dir / origin_auth_repo.name)
    lvc_path = Path(client_auth_repo.conf_dir, client_auth_repo.LAST_VALIDATED_FILENAME)
    assert lvc_path.is_file()
    lvc_path.unlink()

    # Update should still succeed — re-validates from scratch
    update_and_check_commit_shas(
        OperationType.UPDATE,
        origin_auth_repo,
        client_dir,
        expected_repo_type=expected_repo_type,
        skip_check_last_validated=True,
    )
    verify_repos_exist(client_dir, origin_auth_repo)
