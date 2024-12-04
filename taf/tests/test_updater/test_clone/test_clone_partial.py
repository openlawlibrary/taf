import pytest
from taf.tests.test_updater.update_utils import (
    update_and_check_commit_shas,
    verify_repos_exist,
)
from taf.updater.updater import OperationType, UpdateType
from taf.tests.test_updater.conftest import (
    SetupManager,
    add_valid_target_commits,
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
def test_clone_with_excluded_targets(origin_auth_repo, client_dir):

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
        excluded_target_globs=["*/target_same*"],
    )
    verify_repos_exist(
        client_dir, origin_auth_repo, excluded=["target_same1", "target_same2"]
    )
