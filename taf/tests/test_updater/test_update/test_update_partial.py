import pytest
from taf.auth_repo import AuthenticationRepository
from taf.tests.test_updater.conftest import (
    SetupManager,
    add_valid_target_commits,
    set_head_commit,
    update_target_repo_without_committing,
)
from taf.tests.test_updater.update_utils import (
    clone_repositories,
    update_and_check_commit_shas,
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
