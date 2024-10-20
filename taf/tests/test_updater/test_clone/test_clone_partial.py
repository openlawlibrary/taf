import pytest
from taf.tests.test_updater.update_utils import update_and_check_commit_shas
from taf.updater.updater import OperationType, UpdateType
from taf.tests.test_updater.conftest import AuthenticationRepository, SetupManager, add_valid_target_commits, set_head_commit


@pytest.mark.parametrize(
    "origin_auth_repo",
    [
        {
            "targets_config": [{"name": "target_same1"}, {"name": "target_same2"}, {"name": "target_different"}],
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
        excluded_target_globs=["*/target_same*"]
    )

    # client_auth_repo_path = client_dir / origin_auth_repo.name
    # client_auth_repo = AuthenticationRepository(path=client_auth_repo_path)

    # setup_manager = SetupManager(origin_auth_repo)
    # setup_manager.add_task(add_valid_target_commits)
    # setup_manager.execute_tasks()

    # setup_manager.add_task(set_head_commit)

    # setup_manager.add_task(add_valid_target_commits)
    # setup_manager.execute_tasks()

    # setup_manager = SetupManager(client_auth_repo)
    # setup_manager.add_task(
    #     update_target_repo_without_committing, kwargs={"target_name": "target1"}
    # )
    # setup_manager.execute_tasks()

    # update_and_check_commit_shas(
    #     OperationType.UPDATE,
    #     origin_auth_repo,
    #     client_dir,
    #     force=True,
    # )
