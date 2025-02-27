from taf.auth_repo import AuthenticationRepository
import pytest
from taf.updater.types.update import OperationType, UpdateType
from taf.tests.test_updater.update_utils import (
    clone_repositories,
    load_target_repositories,
    update_and_check_commit_shas,
    update_invalid_repos_and_check_if_repos_exist,
    verify_client_repos_state,
    verify_partial_auth_update,
)
from taf.tests.test_updater.conftest import (
    SetupManager,
    add_unauthenticated_commits_to_all_target_repos,
    add_valid_target_commits,
    pull_all_target_repos,
    pull_client_auth_repo,
    pull_specific_target_repo,
    remove_commits,
    update_expiration_dates,
    update_timestamp_metadata_invalid_signature,
)

from taf.tests.test_updater.update_utils import verify_partial_targets_update


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
    Sync client's auth repo with remote without running the updater.
    Run the updater. Expect and check that all repositories were successfully updated to the last remote commit.
    """
    clone_repositories(origin_auth_repo, client_dir)
    client_auth_repo = AuthenticationRepository(client_dir, origin_auth_repo.name)

    setup_manager = SetupManager(origin_auth_repo)
    setup_manager.add_task(update_expiration_dates)
    setup_manager.add_task(add_valid_target_commits)
    setup_manager.execute_tasks()

    assert client_auth_repo.head_commit() != origin_auth_repo.head_commit()

    setup_manager.add_task(pull_client_auth_repo, kwargs={"client_dir": client_dir})
    setup_manager.execute_tasks()

    client_auth_commit = client_auth_repo.head_commit()
    assert client_auth_commit == origin_auth_repo.head_commit()

    update_and_check_commit_shas(OperationType.UPDATE, origin_auth_repo, client_dir)
    verify_client_repos_state(client_dir, origin_auth_repo)


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
    The client's authentication repository is at the last validated commits,
    but the target repositories have additional commits that follow the last validated ones.
    This simulates a scenario where someone used `git pull` to update one or more target repositories.
    """
    clone_repositories(
        origin_auth_repo,
        client_dir,
    )

    client_auth_repo = AuthenticationRepository(client_dir, origin_auth_repo.name)
    origin_target_repos = load_target_repositories(origin_auth_repo)
    client_target_repos = load_target_repositories(client_auth_repo)

    setup_manager = SetupManager(origin_auth_repo)
    setup_manager.add_task(add_valid_target_commits)
    setup_manager.add_task(update_expiration_dates)
    setup_manager.execute_tasks()

    for target_name in origin_target_repos:
        assert (
            origin_target_repos[target_name].head_commit()
            != client_target_repos[target_name].head_commit()
        )

    setup_manager.add_task(pull_all_target_repos, kwargs={"client_dir": client_dir})
    setup_manager.execute_tasks()

    for target_name in origin_target_repos:
        assert (
            origin_target_repos[target_name].head_commit()
            == client_target_repos[target_name].head_commit()
        )

    # Run the updater to update repositories
    update_and_check_commit_shas(
        OperationType.UPDATE,
        origin_auth_repo,
        client_dir,
    )
    verify_client_repos_state(client_dir, origin_auth_repo)


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
    Clients' auth repo has been manually updated.
    The update should result in a partial update where there are invalid commits among the ones that the client pulled.
    Clients' auth repo should be reverted to the last valid commit,
    last validated commits set to that value, and target repositories
    updated up to commits listed in the auth repo's last validated commits.
    """
    clone_repositories(origin_auth_repo, client_dir)

    client_auth_repo = AuthenticationRepository(client_dir, origin_auth_repo.name)

    setup_manager = SetupManager(origin_auth_repo)
    setup_manager.add_task(add_valid_target_commits)
    setup_manager.add_task(update_timestamp_metadata_invalid_signature)
    setup_manager.execute_tasks()

    assert client_auth_repo.head_commit() != origin_auth_repo.head_commit()

    setup_manager.add_task(pull_client_auth_repo, kwargs={"client_dir": client_dir})
    setup_manager.execute_tasks()

    assert client_auth_repo.head_commit() == origin_auth_repo.head_commit()

    update_invalid_repos_and_check_if_repos_exist(
        OperationType.UPDATE,
        origin_auth_repo,
        client_dir,
        None,
        True,
    )
    verify_partial_auth_update(client_dir, origin_auth_repo)
    verify_client_repos_state(client_dir, origin_auth_repo)


@pytest.mark.parametrize(
    "origin_auth_repo",
    [
        {
            "targets_config": [
                {"name": "target1"},
                {"name": "target2"},
            ],
        },
    ],
    indirect=True,
)
def test_target_repo_not_in_sync_partial(origin_auth_repo, client_dir):
    """
    Same as 2, but target repositories contain invalid commits following commits which were manually pulled using git pull.
    Expect all repositories to be updated up to the last validated commits and invalid commits to be removed
    """
    clone_repositories(
        origin_auth_repo,
        client_dir,
    )

    client_auth_repo = AuthenticationRepository(client_dir, origin_auth_repo.name)
    origin_target_repos = load_target_repositories(origin_auth_repo)
    client_target_repos = load_target_repositories(client_auth_repo)

    setup_manager = SetupManager(origin_auth_repo)
    setup_manager.add_task(add_valid_target_commits)
    setup_manager.add_task(add_unauthenticated_commits_to_all_target_repos)
    setup_manager.add_task(add_valid_target_commits)
    setup_manager.execute_tasks()

    for target_name in origin_target_repos:
        assert (
            origin_target_repos[target_name].head_commit()
            != client_target_repos[target_name].head_commit()
        )

    setup_manager.add_task(pull_all_target_repos, kwargs={"client_dir": client_dir})
    setup_manager.execute_tasks()

    for target_name in origin_target_repos:
        assert (
            origin_target_repos[target_name].head_commit()
            == client_target_repos[target_name].head_commit()
        )

    update_invalid_repos_and_check_if_repos_exist(
        OperationType.UPDATE,
        origin_auth_repo,
        client_dir,
        None,
        True,
    )

    verify_partial_auth_update(client_dir, origin_auth_repo)
    verify_partial_targets_update(client_dir, origin_auth_repo)
    verify_client_repos_state(client_dir, origin_auth_repo)


@pytest.mark.parametrize(
    "origin_auth_repo",
    [
        {
            "targets_config": [
                {"name": "target1", "allow_unauthenticated_commits": True},
                {"name": "target2", "allow_unauthenticated_commits": True},
            ]
        },
    ],
    indirect=True,
)
def test_mixed_target_repo_states(origin_auth_repo, client_dir):
    """
    Client's auth repo is on last validated commit, but target commits are all over the place.
    Some are after last validated, some are before.
    """

    setup_manager = SetupManager(origin_auth_repo)
    setup_manager.add_task(add_valid_target_commits)
    setup_manager.add_task(add_valid_target_commits)
    setup_manager.execute_tasks()

    update_and_check_commit_shas(
        OperationType.CLONE,
        origin_auth_repo,
        client_dir,
        expected_repo_type=UpdateType.EITHER,
    )

    client_auth_repo = AuthenticationRepository(client_dir, origin_auth_repo.name)
    origin_target_repos = load_target_repositories(origin_auth_repo)
    client_target_repos = load_target_repositories(client_auth_repo)

    client_target_repos = list(client_target_repos.values())
    reverted_repo = client_target_repos[0]  # target1
    updated_repo = client_target_repos[1]  # target2
    old_commit = reverted_repo.head_commit()

    setup_manager.add_task(add_valid_target_commits)

    setup_manager.add_task(
        remove_commits, kwargs={"repo_path": reverted_repo.path, "num_commits": 1}
    )
    setup_manager.add_task(
        pull_specific_target_repo, kwargs={"repo_path": updated_repo.path}
    )
    setup_manager.execute_tasks()

    setup_manager.add_task(pull_client_auth_repo, kwargs={"client_dir": client_dir})
    setup_manager.execute_tasks()

    updated_repo.head_commit() == origin_target_repos[updated_repo.name].head_commit()
    reverted_repo.head_commit() != old_commit

    update_and_check_commit_shas(
        OperationType.UPDATE, origin_auth_repo, client_dir, force=True
    )

    verify_client_repos_state(client_dir, origin_auth_repo)


@pytest.mark.parametrize(
    "origin_auth_repo",
    [
        {
            "targets_config": [
                {"name": "target1", "allow_unauthenticated_commits": True},
                {"name": "target2", "allow_unauthenticated_commits": True},
            ],
        }
    ],
    indirect=True,
)
def test_update_when_unauthenticated_allowed_different_commits_on_remote(
    origin_auth_repo, client_dir
):
    clone_repositories(
        origin_auth_repo,
        client_dir,
    )
    setup_manager = SetupManager(origin_auth_repo)
    setup_manager.add_task(add_unauthenticated_commits_to_all_target_repos)
    setup_manager.execute_tasks()

    client_auth_repo = AuthenticationRepository(client_dir, origin_auth_repo.name)
    setup_manager = SetupManager(client_auth_repo)
    setup_manager.add_task(add_unauthenticated_commits_to_all_target_repos)
    setup_manager.execute_tasks()

    target_repos = load_target_repositories(client_auth_repo)
    num_of_commits_to_remove = {target_repo: 1 for target_repo in target_repos}

    update_and_check_commit_shas(
        OperationType.UPDATE,
        origin_auth_repo,
        client_dir,
        force=True,
        num_of_commits_to_remove=num_of_commits_to_remove,
    )
