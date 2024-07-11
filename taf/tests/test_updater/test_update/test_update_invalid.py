import pytest
from taf.tests.test_updater.conftest import (
    TARGET_MISSMATCH_PATTERN,
    UNCOIMITTED_CHANGES,
    SetupManager,
    add_file_without_commit,
    add_unauthenticated_commits_to_all_target_repos,
    add_valid_target_commits,
    create_index_lock,
    update_file_without_commit,
    remove_commits,
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
def test_update_invalid_target_repositories_contain_unsigned_commits(
    origin_auth_repo, client_dir
):

    clone_repositories(
        origin_auth_repo,
        client_dir,
    )

    setup_manager = SetupManager(origin_auth_repo)
    setup_manager.add_task(add_valid_target_commits)
    setup_manager.add_task(add_unauthenticated_commits_to_all_target_repos)
    setup_manager.add_task(add_valid_target_commits)
    setup_manager.execute_tasks()

    update_invalid_repos_and_check_if_repos_exist(
        OperationType.UPDATE,
        origin_auth_repo,
        client_dir,
        TARGET_MISSMATCH_PATTERN,
        True,
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
def test_update_invalid_repo_target_in_indeterminate_state(
    origin_auth_repo, client_dir
):
    clone_repositories(
        origin_auth_repo,
        client_dir,
    )

    create_index_lock(origin_auth_repo, client_dir)

    update_invalid_repos_and_check_if_repos_exist(
        OperationType.UPDATE,
        origin_auth_repo,
        client_dir,
        UNCOIMITTED_CHANGES,
        True,
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
def test_dirty_index_auth_repo_update_file(origin_auth_repo, client_dir):
    clone_repositories(
        origin_auth_repo,
        client_dir,
    )

    auth_repo_path = origin_auth_repo.path / "namespace/auth_repo"
    update_file_without_commit(str(auth_repo_path), "dirty_file.txt", "update content")

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
def test_dirty_index_auth_repo_add_file(origin_auth_repo, client_dir):
    clone_repositories(
        origin_auth_repo,
        client_dir,
    )

    auth_repo_path = origin_auth_repo.path / "namespace/auth_repo"
    add_file_without_commit(str(auth_repo_path), "new_file.txt", "new file content")

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
def test_dirty_index_target_repo_update_file(origin_auth_repo, client_dir):
    clone_repositories(
        origin_auth_repo,
        client_dir,
    )

    target_repo_path = origin_auth_repo.path / "namespace/target1"
    update_file_without_commit(
        str(target_repo_path), "dirty_file.txt", "update content"
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
def test_dirty_index_target_repo_add_file(origin_auth_repo, client_dir):
    clone_repositories(
        origin_auth_repo,
        client_dir,
    )

    target_repo_path = origin_auth_repo.path / "namespace/target1"
    add_file_without_commit(str(target_repo_path), "new_file.txt", "new file content")

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
def test_remove_commits_from_target_repo(origin_auth_repo, client_dir):
    clone_repositories(
        origin_auth_repo,
        client_dir,
    )

    target_repo_path = (
        origin_auth_repo.path / "targets/test_remove_commits_from_target_repo0/target1"
    )

    remove_commits(
        str(target_repo_path),
        1,
        repo_name="targets/test_remove_commits_from_target_repo0/target1",
    )

    update_and_check_commit_shas(
        OperationType.UPDATE,
        origin_auth_repo,
        client_dir,
    )
