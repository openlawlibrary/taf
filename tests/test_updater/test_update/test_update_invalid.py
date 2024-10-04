import pytest
from taf.auth_repo import AuthenticationRepository
from taf.tests.test_updater.conftest import (
    INVALID_KEYS_PATTERN,
    TARGET_MISSMATCH_PATTERN,
    FORCED_UPDATE_PATTERN,
    UNCOMMITTED_CHANGES,
    COMMIT_NOT_FOUND_PATTERN,
    SetupManager,
    add_file_without_commit,
    add_unauthenticated_commits_to_all_target_repos,
    add_valid_target_commits,
    create_index_lock,
    update_expiration_dates,
    update_file_without_commit,
    update_role_metadata_invalid_signature,
)
from taf.tests.test_updater.update_utils import (
    check_if_last_validated_commit_exists,
    clone_repositories,
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
        UNCOMMITTED_CHANGES,
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

    client_auth_repo_path = client_dir / origin_auth_repo.name
    update_file_without_commit(str(client_auth_repo_path), "dirty_file.txt")

    update_invalid_repos_and_check_if_repos_exist(
        OperationType.UPDATE,
        origin_auth_repo,
        client_dir,
        FORCED_UPDATE_PATTERN,
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
def test_dirty_index_auth_repo_add_file(origin_auth_repo, client_dir):
    clone_repositories(
        origin_auth_repo,
        client_dir,
    )
    client_auth_repo_path = client_dir / origin_auth_repo.name
    add_file_without_commit(str(client_auth_repo_path), "new_file.txt")

    update_invalid_repos_and_check_if_repos_exist(
        OperationType.UPDATE,
        origin_auth_repo,
        client_dir,
        FORCED_UPDATE_PATTERN,
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
def test_dirty_index_target_repo_update_file(origin_auth_repo, client_dir):
    clone_repositories(
        origin_auth_repo,
        client_dir,
    )

    client_target_repo_path = client_dir / origin_auth_repo.name / "namespace/target1"
    update_file_without_commit(str(client_target_repo_path), "dirty_file.txt")

    update_invalid_repos_and_check_if_repos_exist(
        OperationType.UPDATE,
        origin_auth_repo,
        client_dir,
        FORCED_UPDATE_PATTERN,
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
def test_dirty_index_target_repo_add_file(origin_auth_repo, client_dir):
    clone_repositories(
        origin_auth_repo,
        client_dir,
    )

    client_target_repo_path = client_dir / origin_auth_repo.name / "namespace/target1"
    add_file_without_commit(str(client_target_repo_path), "new_file.txt")

    update_invalid_repos_and_check_if_repos_exist(
        OperationType.UPDATE,
        origin_auth_repo,
        client_dir,
        FORCED_UPDATE_PATTERN,
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
def test_update_invalid_when_repos_not_clean(origin_auth_repo, client_dir):
    clone_repositories(
        origin_auth_repo,
        client_dir,
    )
    client_auth_repo_path = client_dir / origin_auth_repo.name

    update_file_without_commit(str(client_auth_repo_path), "dirty_file.txt")

    update_invalid_repos_and_check_if_repos_exist(
        OperationType.UPDATE,
        origin_auth_repo,
        client_dir,
        FORCED_UPDATE_PATTERN,
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
def test_update_with_invalid_last_validated_commit(origin_auth_repo, client_dir):
    clone_repositories(origin_auth_repo, client_dir)

    invalid_commit_sha = "66d7f48e972f9fa25196523f469227dfcd85c994"
    client_auth_repo = AuthenticationRepository(client_dir, origin_auth_repo.name)
    client_auth_repo.set_last_validated_commit(invalid_commit_sha)

    update_invalid_repos_and_check_if_repos_exist(
        OperationType.UPDATE,
        origin_auth_repo,
        client_dir,
        COMMIT_NOT_FOUND_PATTERN,
        True,
    )


@pytest.mark.parametrize(
    "origin_auth_repo",
    [
        {
            "targets_config": [{"name": "target1"}, {"name": "target2"}],
        }
    ],
    indirect=True,
)
def test_update_invalid_target_invalid_singature(origin_auth_repo, client_dir):

    clone_repositories(origin_auth_repo, client_dir)

    setup_manager = SetupManager(origin_auth_repo)
    setup_manager.add_task(
        update_role_metadata_invalid_signature, kwargs={"role": "targets"}
    )
    setup_manager.add_task(update_expiration_dates)
    setup_manager.execute_tasks()

    update_invalid_repos_and_check_if_repos_exist(
        OperationType.UPDATE,
        origin_auth_repo,
        client_dir,
        INVALID_KEYS_PATTERN,
        True,
    )
    client_auth_repo = AuthenticationRepository(client_dir, origin_auth_repo.name)
    # make sure that the last validated commit does not exist
    check_if_last_validated_commit_exists(client_auth_repo, True)
