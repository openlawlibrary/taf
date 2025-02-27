import pytest
from taf.auth_repo import AuthenticationRepository
from taf.git import GitRepository
from taf.tests.test_updater.conftest import (
    BEHIND_LVC_PATTERN,
    FORCED_UPDATE_PATTERN,
    LVC_NOT_IN_REPO_PATTERN,
    UNPUSHED_COMMITS_PATTERN,
    SetupManager,
    add_file_to_auth_repo_without_committing,
    add_file_to_target_repo_without_committing,
    add_unauthenticated_commit_to_target_repo,
    add_valid_target_commits,
    create_new_target_repo_branch,
    remove_commits,
    remove_commits_from_auth_repo,
    reset_to_commit,
    set_last_commit_of_auth_repo,
    update_auth_repo_without_committing,
    update_expiration_dates,
    update_target_repo_without_committing,
)
from taf.tests.test_updater.update_utils import (
    clone_repositories,
    update_and_check_commit_shas,
    update_invalid_repos_and_check_if_repos_exist,
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
def test_update_valid_dirty_index_auth_repo(origin_auth_repo, client_dir):
    clone_repositories(
        origin_auth_repo,
        client_dir,
    )

    client_auth_repo_path = client_dir / origin_auth_repo.name
    client_auth_repo = AuthenticationRepository(path=client_auth_repo_path)

    setup_manager = SetupManager(client_auth_repo)
    setup_manager.add_task(update_auth_repo_without_committing)
    setup_manager.execute_tasks()
    assert client_auth_repo.something_to_commit()

    # the update should fail without the force flag
    update_invalid_repos_and_check_if_repos_exist(
        OperationType.UPDATE,
        origin_auth_repo,
        client_dir,
        FORCED_UPDATE_PATTERN,
        True,
    )

    # now call with the force flag
    update_and_check_commit_shas(
        OperationType.UPDATE,
        origin_auth_repo,
        client_dir,
        force=True,
    )

    assert not client_auth_repo.something_to_commit()

    setup_manager.add_task(add_file_to_auth_repo_without_committing)
    setup_manager.execute_tasks()

    assert client_auth_repo.something_to_commit()

    # the update should fail without the force flag
    update_invalid_repos_and_check_if_repos_exist(
        OperationType.UPDATE,
        origin_auth_repo,
        client_dir,
        FORCED_UPDATE_PATTERN,
        True,
    )

    update_and_check_commit_shas(
        OperationType.UPDATE,
        origin_auth_repo,
        client_dir,
        force=True,
    )
    assert not client_auth_repo.something_to_commit()


@pytest.mark.parametrize(
    "origin_auth_repo",
    [
        {
            "targets_config": [{"name": "target1"}, {"name": "target2"}],
        },
    ],
    indirect=True,
)
def test_update_valid_dirty_index_target_repo(origin_auth_repo, client_dir):
    clone_repositories(
        origin_auth_repo,
        client_dir,
    )
    client_auth_repo_path = client_dir / origin_auth_repo.name
    client_auth_repo = AuthenticationRepository(path=client_auth_repo_path)

    setup_manager = SetupManager(client_auth_repo)
    setup_manager.add_task(
        update_target_repo_without_committing, kwargs={"target_name": "target1"}
    )
    setup_manager.execute_tasks()

    target1 = GitRepository(path=(client_auth_repo_path.parent / "target1"))
    assert target1.something_to_commit()

    # the update should fail without the force flag
    update_invalid_repos_and_check_if_repos_exist(
        OperationType.UPDATE,
        origin_auth_repo,
        client_dir,
        FORCED_UPDATE_PATTERN,
        True,
    )

    # now call with the force flag
    update_and_check_commit_shas(
        OperationType.UPDATE,
        origin_auth_repo,
        client_dir,
        force=True,
    )

    assert not target1.something_to_commit()

    setup_manager.add_task(
        add_file_to_target_repo_without_committing, kwargs={"target_name": "target1"}
    )
    setup_manager.execute_tasks()

    assert target1.something_to_commit()

    # the update should fail without the force flag
    update_invalid_repos_and_check_if_repos_exist(
        OperationType.UPDATE,
        origin_auth_repo,
        client_dir,
        FORCED_UPDATE_PATTERN,
        True,
    )

    update_and_check_commit_shas(
        OperationType.UPDATE,
        origin_auth_repo,
        client_dir,
        force=True,
    )
    assert not target1.something_to_commit()


@pytest.mark.parametrize(
    "origin_auth_repo",
    [
        {
            "targets_config": [{"name": "target1"}, {"name": "target2"}],
        },
    ],
    indirect=True,
)
def test_update_unpushed_commits_auth_repo(origin_auth_repo, client_dir):
    clone_repositories(
        origin_auth_repo,
        client_dir,
    )

    client_auth_repo_path = client_dir / origin_auth_repo.name
    client_auth_repo = AuthenticationRepository(path=client_auth_repo_path)

    setup_manager = SetupManager(client_auth_repo)
    setup_manager.add_task(update_expiration_dates, kwargs={"push": False})
    setup_manager.execute_tasks()

    has_unpushed, _ = client_auth_repo.branch_unpushed_commits(
        client_auth_repo.default_branch
    )

    assert has_unpushed

    # the update should fail without the force flag
    update_invalid_repos_and_check_if_repos_exist(
        OperationType.UPDATE,
        origin_auth_repo,
        client_dir,
        UNPUSHED_COMMITS_PATTERN,
        True,
    )

    num_of_commits_to_remove = {client_auth_repo.name: 1}
    # now call with the force flag
    update_and_check_commit_shas(
        OperationType.UPDATE,
        origin_auth_repo,
        client_dir,
        force=True,
        num_of_commits_to_remove=num_of_commits_to_remove,
    )

    has_unpushed, _ = client_auth_repo.branch_unpushed_commits(
        client_auth_repo.default_branch
    )
    assert not has_unpushed


@pytest.mark.parametrize(
    "origin_auth_repo",
    [
        {
            "targets_config": [{"name": "target1"}, {"name": "target2"}],
        },
    ],
    indirect=True,
)
def test_update_unpushed_commits_target_repo(origin_auth_repo, client_dir):
    clone_repositories(
        origin_auth_repo,
        client_dir,
    )

    client_auth_repo_path = client_dir / origin_auth_repo.name
    client_auth_repo = AuthenticationRepository(path=client_auth_repo_path)
    client_target_repo_path = client_auth_repo_path.parent / "target1"
    client_target_repo = GitRepository(path=client_target_repo_path)

    setup_manager = SetupManager(client_auth_repo)
    setup_manager.add_task(
        add_unauthenticated_commit_to_target_repo,
        kwargs={"target_name": client_target_repo.name},
    )
    setup_manager.execute_tasks()
    has_unpushed, _ = client_target_repo.branch_unpushed_commits(
        client_target_repo.default_branch
    )
    assert has_unpushed

    # the update should fail without the force flag
    update_invalid_repos_and_check_if_repos_exist(
        OperationType.UPDATE,
        origin_auth_repo,
        client_dir,
        UNPUSHED_COMMITS_PATTERN,
        True,
    )

    num_of_commits_to_remove = {client_target_repo.name: 1}
    # now call with the force flag
    update_and_check_commit_shas(
        OperationType.UPDATE,
        origin_auth_repo,
        client_dir,
        force=True,
        num_of_commits_to_remove=num_of_commits_to_remove,
    )

    has_unpushed, _ = client_target_repo.branch_unpushed_commits(
        client_target_repo.default_branch
    )

    assert not has_unpushed


@pytest.mark.parametrize(
    "origin_auth_repo",
    [
        {
            "targets_config": [{"name": "target1"}, {"name": "target2"}],
        },
    ],
    indirect=True,
)
def test_update_valid_when_detached_head(origin_auth_repo, client_dir):
    clone_repositories(
        origin_auth_repo,
        client_dir,
    )
    client_auth_repo_path = client_dir / origin_auth_repo.name
    client_auth_repo = AuthenticationRepository(path=client_auth_repo_path)

    setup_manager = SetupManager(origin_auth_repo)
    setup_manager.add_task(update_expiration_dates)
    setup_manager.add_task(update_expiration_dates)
    setup_manager.add_task(update_expiration_dates)
    setup_manager.execute_tasks()

    update_output = update_and_check_commit_shas(
        OperationType.UPDATE,
        origin_auth_repo,
        client_dir,
        force=True,
    )

    assert not len(update_output["auth_repos"][client_auth_repo.name]["warnings"])

    all_commits = client_auth_repo.all_commits_on_branch(
        client_auth_repo.default_branch
    )

    clients_setup_manager = SetupManager(client_auth_repo)
    clients_setup_manager.add_task(reset_to_commit, kwargs={"commit": all_commits[-2]})
    clients_setup_manager.add_task(
        set_last_commit_of_auth_repo, kwargs={"commit": all_commits[-2]}
    )
    clients_setup_manager.execute_tasks()

    client_auth_repo.checkout_commit(all_commits[-3])
    assert client_auth_repo.is_detached_head
    assert (
        client_auth_repo.top_commit_of_branch(client_auth_repo.default_branch)
        == all_commits[-2]
    )

    update_output = update_and_check_commit_shas(
        OperationType.UPDATE,
        origin_auth_repo,
        client_dir,
        force=False,
    )
    assert len(update_output["auth_repos"][client_auth_repo.name]["warnings"])

    assert client_auth_repo.is_detached_head
    assert (
        client_auth_repo.top_commit_of_branch(client_auth_repo.default_branch)
        == all_commits[-1]
    )

    update_output = update_and_check_commit_shas(
        OperationType.UPDATE,
        origin_auth_repo,
        client_dir,
        force=True,
    )
    assert not client_auth_repo.is_detached_head
    assert (
        client_auth_repo.top_commit_of_branch(client_auth_repo.default_branch)
        == all_commits[-1]
    )
    assert not len(update_output["auth_repos"][client_auth_repo.name]["warnings"])


@pytest.mark.parametrize(
    "origin_auth_repo",
    [
        {
            "targets_config": [{"name": "target1"}, {"name": "target2"}],
        },
    ],
    indirect=True,
)
def test_update_valid_when_detached_head_target(origin_auth_repo, client_dir):
    # Set up a scenario where repositories
    clone_repositories(
        origin_auth_repo,
        client_dir,
    )
    client_auth_repo_path = client_dir / origin_auth_repo.name
    client_auth_repo = AuthenticationRepository(path=client_auth_repo_path)

    setup_manager = SetupManager(origin_auth_repo)
    setup_manager.add_task(add_valid_target_commits)
    setup_manager.add_task(add_valid_target_commits)
    setup_manager.add_task(add_valid_target_commits)
    setup_manager.execute_tasks()

    update_output = update_and_check_commit_shas(
        OperationType.UPDATE,
        origin_auth_repo,
        client_dir,
        force=True,
    )

    assert not len(update_output["auth_repos"][client_auth_repo.name]["warnings"])

    client_auth_repo_path = GitRepository(client_dir, origin_auth_repo.name).path
    client_target_repo_path = client_auth_repo_path.parent / "target1"
    client_target_repo = GitRepository(path=client_target_repo_path)
    all_commits = client_target_repo.all_commits_on_branch(
        client_auth_repo.default_branch
    )
    client_target_repo.reset_to_commit(all_commits[-2], hard=True)
    client_target_repo.checkout_commit(all_commits[-3])
    assert client_target_repo.is_detached_head
    assert (
        client_target_repo.top_commit_of_branch(client_target_repo.default_branch)
        == all_commits[-2]
    )

    update_output = update_and_check_commit_shas(
        OperationType.UPDATE,
        origin_auth_repo,
        client_dir,
        force=False,
    )

    assert len(update_output["auth_repos"][client_auth_repo.name]["warnings"])

    assert client_target_repo.is_detached_head
    assert (
        client_target_repo.top_commit_of_branch(client_target_repo.default_branch)
        == all_commits[-1]
    )

    update_output = update_and_check_commit_shas(
        OperationType.UPDATE,
        origin_auth_repo,
        client_dir,
        force=True,
    )
    assert not client_target_repo.is_detached_head
    assert (
        client_target_repo.top_commit_of_branch(client_target_repo.default_branch)
        == all_commits[-1]
    )
    assert not len(update_output["auth_repos"][client_auth_repo.name]["warnings"])


@pytest.mark.parametrize(
    "origin_auth_repo",
    [
        {
            "targets_config": [{"name": "target1"}, {"name": "target2"}],
        },
    ],
    indirect=True,
)
def test_update_with_removed_commits_in_auth_repo(origin_auth_repo, client_dir):
    clone_repositories(origin_auth_repo, client_dir)

    setup_manager = SetupManager(origin_auth_repo)
    setup_manager.add_task(add_valid_target_commits)
    setup_manager.execute_tasks()

    client_auth_repo = AuthenticationRepository(client_dir, origin_auth_repo.name)
    remove_commits(
        repo_path=str(client_auth_repo.path),
        num_commits=1,
    )

    update_invalid_repos_and_check_if_repos_exist(
        OperationType.UPDATE,
        origin_auth_repo,
        client_dir,
        BEHIND_LVC_PATTERN,
        True,
    )

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
            "targets_config": [{"name": "target1"}, {"name": "target2"}],
        },
    ],
    indirect=True,
)
def test_update_with_last_validated_commit_not_in_local_repo(
    origin_auth_repo, client_dir
):
    clone_repositories(origin_auth_repo, client_dir)

    setup_manager = SetupManager(origin_auth_repo)
    setup_manager.add_task(add_valid_target_commits)
    setup_manager.execute_tasks()

    origin_top_commit = origin_auth_repo.head_commit()
    client_auth_repo = AuthenticationRepository(client_dir, origin_auth_repo.name)
    clients_setup_manager = SetupManager(client_auth_repo)
    clients_setup_manager.add_task(
        set_last_commit_of_auth_repo, kwargs={"commit": origin_top_commit}
    )
    clients_setup_manager.add_task(remove_commits_from_auth_repo)
    clients_setup_manager.execute_tasks()

    update_invalid_repos_and_check_if_repos_exist(
        OperationType.UPDATE,
        origin_auth_repo,
        client_dir,
        LVC_NOT_IN_REPO_PATTERN,
        True,
    )

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
            "targets_config": [{"name": "target1"}, {"name": "target2"}],
        },
    ],
    indirect=True,
)
def test_update_with_targets_repo_having_a_local_branch_not_on_remote_origin_expect_error(
    origin_auth_repo, client_dir
):
    clone_repositories(origin_auth_repo, client_dir)

    setup_manager = SetupManager(origin_auth_repo)
    setup_manager.add_task(add_valid_target_commits)
    setup_manager.execute_tasks()

    origin_top_commit = origin_auth_repo.head_commit()
    client_auth_repo = AuthenticationRepository(client_dir, origin_auth_repo.name)
    client_auth_repo = AuthenticationRepository(client_dir, origin_auth_repo.name)
    clients_setup_manager = SetupManager(client_auth_repo)
    clients_setup_manager.add_task(
        set_last_commit_of_auth_repo, kwargs={"commit": origin_top_commit}
    )
    clients_setup_manager.add_task(
        create_new_target_repo_branch, kwargs={"target_name": "target1"}
    )
    clients_setup_manager.execute_tasks()

    update_invalid_repos_and_check_if_repos_exist(
        OperationType.UPDATE,
        origin_auth_repo,
        client_dir,
        LVC_NOT_IN_REPO_PATTERN,
        True,
    )

    update_and_check_commit_shas(
        OperationType.UPDATE,
        origin_auth_repo,
        client_dir,
        force=True,
    )
