import pytest
from taf.updater.types.update import OperationType
from taf.tests.test_updater.update_utils import (
    assert_repositories_updated,
    clone_repositories,
    update_and_check_commit_shas,
)
from taf.tests.test_updater.conftest import (
    SetupManager,
    add_valid_target_commits,
    add_valid_unauthenticated_commits,
    remove_commits,
    revert_last_validated_commit,
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
    """
    Client's authentication repository and target repositories are not in sync.
    Authentication repository contains some commits following the last validated commit.
    Target repositories are in sync with the last validated commit - simulate the case when
    someone used git pull to update the authentication repository. In fact, that is probably
    how we want to set this up. Run the updater to clone all repositories (an auth repo and its targets,
    we should not make this more complicated by test the update of a repo with dependencies).
    Make valid changes to both the auth repo and the target repos (only origin repos).
    Sync client's auth repo with remote without running the updater.
    Run the updater. Expect and check that all repositories were successfully updated to the last remote commit.
    """
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
    """
    Client's authentication repository is on last validated commits,
    but target repositories contain commits following the last validated ones.
    Simulate the case when someone used git pull to update the one or more target repositories.
    Run the updater to clone all repositories. Make valid changes to both the auth repo and the target repos (only origin repos).
    Sync one or more target repos with remote without running the updater. Run the updater.
    Expect and check that all repositories were successfully updated to the last remote commit.
    """
    clone_repositories(
        origin_auth_repo,
        client_dir,
    )
    setup_manager = SetupManager(origin_auth_repo)
    setup_manager.add_task(add_valid_target_commits)
    setup_manager.add_task(update_expiration_dates)
    setup_manager.add_task(
        sync_target_repos_with_remote,
        kwargs={"origin_auth_repo": origin_auth_repo, "client_dir": client_dir},
    )
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
    """
    Clients auth repo has been manually updated, just like in 1.
    The update should result in a partial update.
    Clients auth repo should be reverted to the last valid commit,
    last validated commits set to that value,
    target repositories updated up to commits listed in auth repo's last validated commits
    """
    clone_repositories(
        origin_auth_repo,
        client_dir,
    )
    setup_manager = SetupManager(origin_auth_repo)
    setup_manager.add_task(update_expiration_dates)
    setup_manager.add_task(add_valid_target_commits)
    setup_manager.add_task(
        revert_last_validated_commit, kwargs={"client_dir": client_dir}
    )
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
    """
    Same as 2, but target repositories contain invalid commits following commits which were manually pulled using git pull.
    Expect all repositories to be updated up to the last validated commits and invalid commits to be removed
    """
    clone_repositories(
        origin_auth_repo,
        client_dir,
    )
    setup_manager = SetupManager(origin_auth_repo)
    setup_manager.add_task(add_valid_unauthenticated_commits)
    setup_manager.add_task(update_expiration_dates)
    setup_manager.add_task(
        sync_target_repos_with_remote,
        kwargs={"origin_auth_repo": origin_auth_repo, "client_dir": client_dir},
    )
    setup_manager.add_task(
        revert_last_validated_commit, kwargs={"client_dir": client_dir}
    )
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
    """
    Client's auth repo is not on last validated commit, but target commits are all over the place.
    Some are after last validated, some are before.
    At the moment, i believe that the validation will start from the beginning in such a case and will be successful
    if there are no invalid commits.
    """
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
    setup_manager.add_task(
        remove_commits, kwargs={"repo_path": client_target_repo_path, "num_commits": 1}
    )
    setup_manager.add_task(
        revert_last_validated_commit, kwargs={"client_dir": client_dir}
    )
    setup_manager.execute_tasks()
    assert_repositories_updated(client_dir, origin_auth_repo)
