from taf.models.types import Commitish
import pytest
from taf.auth_repo import AuthenticationRepository
from taf.tests.test_updater.conftest import (
    INVALID_KEYS_PATTERN,
    LVC_NOT_IN_REMOTE_PATTERN,
    TARGET_MISSMATCH_PATTERN,
    UNCOMMITTED_CHANGES,
    SetupManager,
    add_unauthenticated_commits_to_all_target_repos,
    add_valid_target_commits,
    create_index_lock,
    set_last_commit_of_auth_repo,
    update_expiration_dates,
    update_timestamp_metadata_invalid_signature,
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
def test_update_with_invalid_last_validated_commit(origin_auth_repo, client_dir):
    clone_repositories(origin_auth_repo, client_dir)

    invalid_commit_sha = Commitish.from_hash("66d7f48e972f9fa25196523f469227dfcd85c994")
    client_auth_repo = AuthenticationRepository(client_dir, origin_auth_repo.name)
    clients_setup_manager = SetupManager(client_auth_repo)
    clients_setup_manager.add_task(
        set_last_commit_of_auth_repo, kwargs={"commit": invalid_commit_sha}
    )
    clients_setup_manager.execute_tasks()

    update_invalid_repos_and_check_if_repos_exist(
        OperationType.UPDATE,
        origin_auth_repo,
        client_dir,
        LVC_NOT_IN_REMOTE_PATTERN,
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
    setup_manager.add_task(update_timestamp_metadata_invalid_signature)
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
