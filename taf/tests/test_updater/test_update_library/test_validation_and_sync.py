import pytest
from taf.updater.types.update import OperationType
from taf.tests.test_updater.update_utils import (
    clone_repositories,
    load_target_repositories,
    update_and_check_commit_shas,
    verify_client_repos_state,
)
from taf.tests.test_updater.conftest import (
    SetupManager,
    add_valid_target_commits,
    add_valid_unauthenticated_commits,
    remove_commits,
    sync_auth_repo,
    sync_target_repos_with_remote,
    update_existing_file,
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
    Sync client's auth repo with remote without running the updater.
    Run the updater. Expect and check that all repositories were successfully updated to the last remote commit.
    """
    clone_repositories(origin_auth_repo, client_dir)
    original_commit = origin_auth_repo.head_commit_sha()

    setup_manager = SetupManager(origin_auth_repo)
    setup_manager.add_task(update_expiration_dates)
    setup_manager.add_task(add_valid_target_commits)
    setup_manager.execute_tasks()

    new_origin_commit = origin_auth_repo.head_commit_sha()
    assert original_commit != new_origin_commit
    setup_manager.add_task(sync_auth_repo)
    setup_manager.execute_tasks()

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
    original_commit = origin_auth_repo.head_commit_sha()

    setup_manager = SetupManager(origin_auth_repo)
    setup_manager.add_task(add_valid_target_commits)
    setup_manager.add_task(update_expiration_dates)
    setup_manager.execute_tasks()

    new_origin_commit = origin_auth_repo.head_commit_sha()
    assert original_commit != new_origin_commit

    setup_manager.add_task(
        sync_target_repos_with_remote,
        kwargs={"origin_auth_repo": origin_auth_repo, "client_dir": client_dir},
    )
    setup_manager.execute_tasks()

    verify_client_repos_state(client_dir, origin_auth_repo)

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

    # Load the target repositories
    target_repos = list(load_target_repositories(origin_auth_repo).values())
    original_commits = {repo.name: repo.head_commit_sha() for repo in target_repos}
    original_commit = origin_auth_repo.head_commit_sha()

    setup_manager = SetupManager(origin_auth_repo)
    setup_manager.add_task(add_valid_unauthenticated_commits)
    setup_manager.add_task(add_valid_target_commits)
    setup_manager.execute_tasks()

    new_commits = {repo.name: repo.head_commit_sha() for repo in target_repos}

    for repo_name in original_commits:
        assert original_commits[repo_name] != new_commits[repo_name]

    # Introduce an invalid signature update
    setup_manager.add_task(update_expiration_dates, kwargs={"repetitions": 2})
    setup_manager.execute_tasks()

    new_origin_commit = origin_auth_repo.head_commit_sha()
    assert original_commit != new_origin_commit

    # Sync auth repo and check if the last validated commit exists
    setup_manager.add_task(sync_auth_repo)
    setup_manager.execute_tasks()

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
def test_target_repo_not_in_sync_partial(origin_auth_repo, client_dir):
    """
    Same as 2, but target repositories contain invalid commits following commits which were manually pulled using git pull.
    Expect all repositories to be updated up to the last validated commits and invalid commits to be removed
    """
    clone_repositories(
        origin_auth_repo,
        client_dir,
    )
    target_repos = list(load_target_repositories(origin_auth_repo).values())
    original_commits = {repo.name: repo.head_commit_sha() for repo in target_repos}

    setup_manager = SetupManager(origin_auth_repo)
    setup_manager.add_task(add_valid_unauthenticated_commits)
    setup_manager.add_task(add_valid_target_commits)
    setup_manager.execute_tasks()

    new_commits = {repo.name: repo.head_commit_sha() for repo in target_repos}
    for repo_name in original_commits:
        assert original_commits[repo_name] != new_commits[repo_name]
    setup_manager.add_task(
        sync_target_repos_with_remote,
        kwargs={"origin_auth_repo": origin_auth_repo, "client_dir": client_dir},
    )
    setup_manager.execute_tasks()

    update_and_check_commit_shas(OperationType.UPDATE, origin_auth_repo, client_dir)
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
    clone_repositories(
        origin_auth_repo,
        client_dir,
    )

    target_repos = list(load_target_repositories(origin_auth_repo).values())
    original_commits = {repo.name: repo.head_commit_sha() for repo in target_repos}
    reverted_repo = target_repos[0]  # target1
    updated_repo = target_repos[1]  # target2

    setup_manager = SetupManager(origin_auth_repo)
    setup_manager.add_task(add_valid_target_commits)
    setup_manager.execute_tasks()

    setup_manager.add_task(
        remove_commits, kwargs={"repo_path": reverted_repo.path, "num_commits": 2}
    )
    setup_manager.add_task(
        update_existing_file,
        kwargs={
            "repo": updated_repo,
            "filename": "test1.txt",
            "commit_message": "Manually update test1.txt",
        },
    )
    setup_manager.execute_tasks()

    # Check that the reverted repo has the same commit as the original
    reverted_commit = reverted_repo.head_commit_sha()
    assert original_commits[reverted_repo.name] == reverted_commit

    # Check that the manually updated repo has a new commit
    updated_commit = updated_repo.head_commit_sha()
    assert original_commits[updated_repo.name] != updated_commit

    # Sync the authentication repo
    setup_manager.add_task(
        sync_target_repos_with_remote,
        kwargs={"origin_auth_repo": origin_auth_repo, "client_dir": client_dir},
    )
    setup_manager.execute_tasks()

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
def test_target_repo_mixed_manual_updates(origin_auth_repo, client_dir):
    """
    Some target repositories are updated manually, and some are not.
    Expect that manually updated repositories have new commits, while others do not.
    """
    clone_repositories(origin_auth_repo, client_dir)

    setup_manager = SetupManager(origin_auth_repo)
    setup_manager.add_task(update_expiration_dates)
    setup_manager.add_task(add_valid_target_commits)
    setup_manager.execute_tasks()
    update_and_check_commit_shas(OperationType.UPDATE, origin_auth_repo, client_dir)

    # Load the target repositories
    target_repos = list(load_target_repositories(origin_auth_repo).values())
    original_commits = {repo.name: repo.head_commit_sha() for repo in target_repos}

    # Manually update one of the target repositories
    manually_updated_repo = target_repos[0]  # Update the first repo (target1)
    untouched_repo = target_repos[1]  # Leave the second repo (target2) untouched

    print(
        f"Original commit of manually updated repo: {original_commits[manually_updated_repo.name]}"
    )
    print(f"Original commit of untouched repo: {original_commits[untouched_repo.name]}")

    # Update the manually updated repository
    setup_manager = SetupManager(origin_auth_repo)
    setup_manager.add_task(
        update_existing_file,
        kwargs={
            "repo": manually_updated_repo,
            "filename": "test1.txt",
            "commit_message": "Manually update test1.txt",
        },
    )
    setup_manager.execute_tasks()

    # Check that the manually updated repo has a new commit
    manually_updated_commit = manually_updated_repo.head_commit_sha()
    assert original_commits[manually_updated_repo.name] != manually_updated_commit

    # Check that the untouched repo has the same commit
    untouched_commit = untouched_repo.head_commit_sha()
    assert original_commits[untouched_repo.name] == untouched_commit

    # Revert the manually updated repository to its original commit
    setup_manager.add_task(
        sync_target_repos_with_remote,
        kwargs={"origin_auth_repo": origin_auth_repo, "client_dir": client_dir},
    )
    setup_manager.execute_tasks()
    # update_and_check_commit_shas(OperationType.UPDATE, origin_auth_repo, client_dir)

    verify_client_repos_state(client_dir, origin_auth_repo)
