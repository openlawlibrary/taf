import pytest
from taf.auth_repo import AuthenticationRepository
from taf.tests.test_updater.conftest import (
    SetupManager,
    add_file_without_commit,
    add_valid_target_commits,
    remove_commits,
    update_expiration_dates,
    update_file_without_commit,
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
def test_update_valid_dirty_index_auth_repo(origin_auth_repo, client_dir):
    clone_repositories(
        origin_auth_repo,
        client_dir,
    )

    client_auth_repo_path = client_dir / origin_auth_repo.name
    update_file_without_commit(str(client_auth_repo_path), "dirty_file.txt")

    update_and_check_commit_shas(
        OperationType.UPDATE,
        origin_auth_repo,
        client_dir,
        force=True,
    )

    add_file_without_commit(str(client_auth_repo_path), "new_file.txt")

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
def test_update_valid_dirty_index_target_repo(origin_auth_repo, client_dir):
    clone_repositories(
        origin_auth_repo,
        client_dir,
    )

    client_target_repo_path = client_dir / origin_auth_repo.name / "namespace/target1"
    update_file_without_commit(str(client_target_repo_path), "dirty_file.txt")

    update_and_check_commit_shas(
        OperationType.UPDATE,
        origin_auth_repo,
        client_dir,
        force=True,
    )

    add_file_without_commit(str(client_target_repo_path), "dirty_file.txt")

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
def test_update_valid_when_detached_head(origin_auth_repo, client_dir):
    # Set up a scenario where repositories
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

    update_and_check_commit_shas(
        OperationType.UPDATE,
        origin_auth_repo,
        client_dir,
        force=True,
    )

    all_commits = client_auth_repo.all_commits_on_branch(
        client_auth_repo.default_branch
    )
    client_auth_repo.reset_to_commit(all_commits[-2], hard=True)
    client_auth_repo.checkout_commit(all_commits[-3])
    assert client_auth_repo.is_detached_head
    assert (
        client_auth_repo.top_commit_of_branch(client_auth_repo.default_branch)
        == all_commits[-2]
    )
    client_auth_repo.set_last_validated_commit(all_commits[-2])

    update_and_check_commit_shas(
        OperationType.UPDATE,
        origin_auth_repo,
        client_dir,
        force=False,
    )

    assert client_auth_repo.is_detached_head
    assert (
        client_auth_repo.top_commit_of_branch(client_auth_repo.default_branch)
        == all_commits[-1]
    )

    update_and_check_commit_shas(
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

    update_and_check_commit_shas(
        OperationType.UPDATE,
        origin_auth_repo,
        client_dir,
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

    origin_top_commit_sha = origin_auth_repo.head_commit_sha()
    client_auth_repo = AuthenticationRepository(client_dir, origin_auth_repo.name)
    client_auth_repo.set_last_validated_commit(origin_top_commit_sha)

    remove_commits(
        repo_path=str(client_auth_repo.path),
        num_commits=1,
    )
    # Skips udpater commit hash checks. Currently the update runs fully but the commit validation fails.
    update_and_check_commit_shas(
        OperationType.UPDATE,
        origin_auth_repo,
        client_dir,
        skip_check_last_validated=True,
    )
