import pytest
from taf.updater.types.update import OperationType
from taf.tests.test_updater.update_utils import (
    assert_repositories_updated,
    clone_repositories,
    update_and_check_commit_shas,
    update_invalid_repos_and_check_if_repos_exist,
)
from taf.tests.test_updater.conftest import (
    TARGET_MISSMATCH_PATTERN,
    SetupManager,
    add_valid_target_commits,
    add_valid_unauthenticated_commits,
    remove_commits,
    sync_auth_repo,
    sync_target_repos_with_remote,
    update_expiration_dates,
)

@pytest.mark.parametrize(
    "origin_auth_repo",
    [
        {
            "targets_config": [
                {"name": "target1", "allow_unauthenticated_commits": True},
                {"name": "target2", "allow_unauthenticated_commits": True},
            ],
        },
    ],
    indirect=True,
)
def test_auth_repo_not_in_sync(origin_auth_repo, client_dir):
    #Test 1
    clone_repositories(
        origin_auth_repo,
        client_dir,
    )
    setup_manager = SetupManager(origin_auth_repo)
    setup_manager.add_task(update_expiration_dates)
    setup_manager.add_task(add_valid_target_commits)
    setup_manager.add_task(sync_auth_repo)
    setup_manager.execute_tasks()
    
    update_and_check_commit_shas(
        OperationType.UPDATE,
        origin_auth_repo,
        client_dir,
    )


@pytest.mark.parametrize(
    "origin_auth_repo",
    [
        {
            "targets_config": [
                {"name": "target1", "allow_unauthenticated_commits": True},
                {"name": "target2", "allow_unauthenticated_commits": True},
            ],
        },
    ],
    indirect=True,
)
def test_target_repo_not_in_sync(origin_auth_repo, client_dir):
    #Test 2
    clone_repositories(
        origin_auth_repo,
        client_dir,
    )
    setup_manager = SetupManager(origin_auth_repo)
    setup_manager.add_task(add_valid_target_commits)
    setup_manager.add_task(update_expiration_dates)
    setup_manager.add_task(sync_target_repos_with_remote, kwargs={"origin_auth_repo": origin_auth_repo, "client_dir": client_dir})
    setup_manager.execute_tasks()

    # Run the updater to update repositories
    update_and_check_commit_shas(
        OperationType.UPDATE,
        origin_auth_repo,
        client_dir,
    )


@pytest.mark.parametrize(
    "origin_auth_repo",
    [
        {
            "targets_config": [
                {"name": "target1", "allow_unauthenticated_commits": True},
                {"name": "target2", "allow_unauthenticated_commits": True},
            ],
        },
    ],
    indirect=True,
)
def test_auth_repo_not_in_sync_partial(origin_auth_repo, client_dir):
    #Test 3
    clone_repositories(
        origin_auth_repo,
        client_dir,
    )
    setup_manager = SetupManager(origin_auth_repo)
    setup_manager.add_task(update_expiration_dates)
    setup_manager.add_task(add_valid_target_commits)
    setup_manager.execute_tasks()
    
    assert_repositories_updated(client_dir, origin_auth_repo)

@pytest.mark.parametrize(
    "origin_auth_repo",
    [
        {
            "targets_config": [
                {"name": "target1", "allow_unauthenticated_commits": True},
                {"name": "target2", "allow_unauthenticated_commits": True},
            ],
        },
    ],
    indirect=True,
)
def test_target_repo_not_in_sync_invalid_commits(origin_auth_repo, client_dir):
    #Test 4
    clone_repositories(
        origin_auth_repo,
        client_dir,
    )
    setup_manager = SetupManager(origin_auth_repo)
    setup_manager.add_task(add_valid_unauthenticated_commits)
    setup_manager.add_task(update_expiration_dates)
    setup_manager.add_task(sync_target_repos_with_remote, kwargs={"origin_auth_repo": origin_auth_repo, "client_dir": client_dir})
    setup_manager.execute_tasks()

    assert_repositories_updated(client_dir, origin_auth_repo)
    

@pytest.mark.parametrize(
    "origin_auth_repo",
    [
        {
            "targets_config": [
                {"name": "target1", "allow_unauthenticated_commits": True},
                {"name": "target2", "allow_unauthenticated_commits": True},
            ],
        },
    ],
    indirect=True,
)
def test_mixed_target_repo_states(origin_auth_repo, client_dir):
    # Test 5
    client_target_repo_path = (
        client_dir
        / origin_auth_repo.name
        / "targets/test_remove_commits_from_target_repo0/target1"
    )

    remove_commits(str(client_target_repo_path))
    clone_repositories(
        origin_auth_repo,
        client_dir,
    )
    setup_manager = SetupManager(origin_auth_repo)
    setup_manager.add_task(add_valid_target_commits)
    setup_manager.add_task(update_expiration_dates)
    setup_manager.add_task(remove_commits, kwargs={"repo_path":client_target_repo_path,"num_commits":1})
    setup_manager.execute_tasks()
    assert_repositories_updated(client_dir, origin_auth_repo)
