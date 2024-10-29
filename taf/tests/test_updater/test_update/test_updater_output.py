import pytest
from taf.auth_repo import AuthenticationRepository
from taf.tests.test_updater.conftest import (
    SetupManager,
    add_valid_target_commits,
    remove_commits,
)
from taf.tests.test_updater.update_utils import (
    clone_repositories,
    load_target_repositories,
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
def test_update_valid_when_several_updates(origin_auth_repo, client_dir):
    clone_repositories(origin_auth_repo, client_dir)

    setup_manager = SetupManager(origin_auth_repo)
    setup_manager.add_task(add_valid_target_commits)
    setup_manager.add_task(add_valid_target_commits)
    setup_manager.add_task(add_valid_target_commits)
    setup_manager.execute_tasks()

    update_output = update_and_check_commit_shas(
        OperationType.UPDATE,
        origin_auth_repo,
        client_dir,
        skip_check_last_validated=True,
    )
    assert update_output["changed"]
    client_auth_repo = AuthenticationRepository(client_dir, origin_auth_repo.name)
    client_target_repos = load_target_repositories(client_auth_repo)
    setup_manager = SetupManager(client_auth_repo)
    for target_repo in client_target_repos.values():
        setup_manager.add_task(
            remove_commits, kwargs={"repo_path": target_repo.path, "num_commits": 1}
        )
        break
    setup_manager.execute_tasks()
    update_output = update_and_check_commit_shas(
        OperationType.UPDATE,
        origin_auth_repo,
        client_dir,
        skip_check_last_validated=True,
    )
    assert update_output["changed"]
    update_output = update_and_check_commit_shas(
        OperationType.UPDATE,
        origin_auth_repo,
        client_dir,
        skip_check_last_validated=True,
    )
    assert not update_output["changed"]
