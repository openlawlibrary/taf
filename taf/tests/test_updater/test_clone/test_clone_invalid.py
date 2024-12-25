import pytest
from taf.auth_repo import AuthenticationRepository
from taf.tests.test_updater.conftest import (
    INVALID_KEYS_PATTERN,
    NO_INFO_JSON,
    TARGET_COMMIT_AFTER_LAST_VALIDATED_PATTERN,
    TARGET_COMMIT_MISMATCH_PATTERN,
    TARGET_MISSMATCH_PATTERN,
    UPDATE_ERROR_PATTERN,
    WRONG_UPDATE_TYPE_OFFICIAL_REPO,
    WRONG_UPDATE_TYPE_TEST_REPO,
    SetupManager,
    SetupState,
    add_unauthenticated_commits_to_all_target_repos,
    add_valid_target_commits,
    clone_client_repo,
    swap_last_two_commits,
    update_expiration_dates,
    update_timestamp_metadata_invalid_signature,
)
from taf.tests.test_updater.update_utils import (
    check_if_last_validated_commit_exists,
    update_invalid_repos_and_check_if_repos_exist,
)
from taf.updater.types.update import OperationType, UpdateType


@pytest.mark.parametrize(
    "origin_auth_repo",
    [
        {
            "targets_config": [{"name": "target1"}, {"name": "target2"}],
        },
    ],
    indirect=True,
)
def test_clone_invalid_target_repositories_top_commits_unsigned(
    origin_auth_repo, client_dir
):

    setup_manager = SetupManager(origin_auth_repo)
    setup_manager.add_task(add_unauthenticated_commits_to_all_target_repos)
    setup_manager.execute_tasks()

    update_invalid_repos_and_check_if_repos_exist(
        OperationType.CLONE,
        origin_auth_repo,
        client_dir,
        TARGET_COMMIT_AFTER_LAST_VALIDATED_PATTERN,
        True,
    )
    client_auth_repo = AuthenticationRepository(client_dir, origin_auth_repo.name)
    # make sure that the last validated commit does not exist
    check_if_last_validated_commit_exists(client_auth_repo, True)


@pytest.mark.parametrize(
    "origin_auth_repo",
    [
        {
            "targets_config": [{"name": "target1"}, {"name": "target2"}],
        },
    ],
    indirect=True,
)
def test_clone_invalid_target_repositories_contain_unsigned_commits(
    origin_auth_repo, client_dir
):

    setup_manager = SetupManager(origin_auth_repo)
    setup_manager.add_task(add_unauthenticated_commits_to_all_target_repos)
    setup_manager.add_task(add_valid_target_commits)
    setup_manager.execute_tasks()

    update_invalid_repos_and_check_if_repos_exist(
        OperationType.CLONE,
        origin_auth_repo,
        client_dir,
        TARGET_MISSMATCH_PATTERN,
        True,
    )
    client_auth_repo = AuthenticationRepository(client_dir, origin_auth_repo.name)
    # make sure that the last validated commit does not exist
    check_if_last_validated_commit_exists(client_auth_repo, True)


@pytest.mark.parametrize(
    "origin_auth_repo",
    [
        {
            "targets_config": [{"name": "target1"}, {"name": "target2"}],
        }
    ],
    indirect=True,
)
def test_clone_invalid_target_invalid_metadata(origin_auth_repo, client_dir):

    setup_manager = SetupManager(origin_auth_repo)
    setup_manager.add_task(update_expiration_dates, kwargs={"repetitions": 2})
    setup_manager.add_task(swap_last_two_commits)
    setup_manager.execute_tasks()

    # On CI, the error message is not always the same, but always reports that the metadata is invalid
    # so use a more generic error pattern for now
    update_invalid_repos_and_check_if_repos_exist(
        OperationType.CLONE,
        origin_auth_repo,
        client_dir,
        UPDATE_ERROR_PATTERN,
        True,
    )
    client_auth_repo = AuthenticationRepository(client_dir, origin_auth_repo.name)
    # make sure that the last validated commit does not exist
    check_if_last_validated_commit_exists(client_auth_repo, True)


@pytest.mark.parametrize(
    "origin_auth_repo, existing_target_repositories",
    [
        (
            {
                "targets_config": [{"name": "target1"}, {"name": "target2"}],
            },
            ["target1"],
        ),
        (
            {
                "targets_config": [{"name": "target1"}, {"name": "target2"}],
            },
            ["target1", "target2"],
        ),
    ],
    indirect=["origin_auth_repo"],
)
def test_clone_invalid_target_repositories_targets_exist(
    origin_auth_repo, existing_target_repositories, client_dir
):

    setup_manager = SetupManager(origin_auth_repo)
    setup_manager.add_task(add_unauthenticated_commits_to_all_target_repos)
    setup_manager.add_task(add_valid_target_commits)
    setup_manager.execute_tasks()

    for existing_repository in existing_target_repositories:
        repo_name = f"{origin_auth_repo.name.split('/')[0]}/{existing_repository}"
        client_repo = clone_client_repo(
            repo_name, origin_auth_repo.path.parent.parent, client_dir
        )
        assert client_repo.path.is_dir()

    update_invalid_repos_and_check_if_repos_exist(
        OperationType.CLONE,
        origin_auth_repo,
        client_dir,
        TARGET_COMMIT_MISMATCH_PATTERN,
        True,
    )
    client_auth_repo = AuthenticationRepository(client_dir, origin_auth_repo.name)
    # make sure that the last validated commit does not exist
    check_if_last_validated_commit_exists(client_auth_repo, True)


@pytest.mark.parametrize(
    "origin_auth_repo",
    [
        {
            "targets_config": [{"name": "target1"}, {"name": "target2"}],
        }
    ],
    indirect=True,
)
def test_clone_invalid_target_invalid_singature(origin_auth_repo, client_dir):

    setup_manager = SetupManager(origin_auth_repo)
    setup_manager.add_task(update_timestamp_metadata_invalid_signature)
    setup_manager.execute_tasks()

    update_invalid_repos_and_check_if_repos_exist(
        OperationType.CLONE,
        origin_auth_repo,
        client_dir,
        INVALID_KEYS_PATTERN,
        True,
    )
    client_auth_repo = AuthenticationRepository(client_dir, origin_auth_repo.name)
    # make sure that the last validated commit does not exist
    check_if_last_validated_commit_exists(client_auth_repo, True)


@pytest.mark.parametrize(
    "origin_auth_repo",
    [
        {
            "targets_config": [{"name": "target1"}, {"name": "target2"}],
            "is_test_repo": False,
        }
    ],
    indirect=True,
)
def test_clone_invalid_wrong_update_type_when_official_repo(
    origin_auth_repo, client_dir
):

    update_invalid_repos_and_check_if_repos_exist(
        OperationType.CLONE,
        origin_auth_repo,
        client_dir,
        WRONG_UPDATE_TYPE_OFFICIAL_REPO,
        False,
        expected_repo_type=UpdateType.TEST,
    )
    client_auth_repo = AuthenticationRepository(client_dir, origin_auth_repo.name)
    # make sure that the last validated commit does not exist
    check_if_last_validated_commit_exists(client_auth_repo, False)


@pytest.mark.parametrize(
    "origin_auth_repo",
    [
        {
            "targets_config": [{"name": "target1"}, {"name": "target2"}],
            "is_test_repo": True,
        },
    ],
    indirect=True,
)
def test_clone_invalid_wrong_update_type_when_test_repo(origin_auth_repo, client_dir):
    update_invalid_repos_and_check_if_repos_exist(
        OperationType.CLONE,
        origin_auth_repo,
        client_dir,
        WRONG_UPDATE_TYPE_TEST_REPO,
        False,
        expected_repo_type=UpdateType.OFFICIAL,
    )
    client_auth_repo = AuthenticationRepository(client_dir, origin_auth_repo.name)
    # make sure that the last validated commit does not exist
    check_if_last_validated_commit_exists(client_auth_repo, False)


@pytest.mark.parametrize(
    "origin_auth_repo",
    [
        {
            "setup_type": SetupState.NO_INFO_JSON,
            "targets_config": [{"name": "target1"}, {"name": "target2"}],
        },
    ],
    indirect=True,
)
def test_clone_invalid_when_no_info_json_and_no_path(origin_auth_repo, client_dir):

    update_invalid_repos_and_check_if_repos_exist(
        OperationType.CLONE,
        origin_auth_repo,
        client_dir,
        NO_INFO_JSON,
        expect_partial_update=False,
        auth_repo_name_exists=False,
    )
    client_auth_repo = AuthenticationRepository(client_dir, origin_auth_repo.name)
    # make sure that the last validated commit does not exist
    check_if_last_validated_commit_exists(client_auth_repo, False)


# # @pytest.mark.parametrize(
# #     "test_name, expected_error, repo_name_exists, expect_partial_update, should_last_validated_exist",
# #     [
# #         # TODO: re-enable when old-snapshot validation is fully supported
# #         # Issue: https://github.com/openlawlibrary/taf/issues/385
# #         # (
# #         #     "test-updater-updated-root-old-snapshot",
# #         #     INVALID_METADATA_PATTERN,
# #         #     True,
# #         #     False,
# #         #     False,
# #         # ),
# # )
