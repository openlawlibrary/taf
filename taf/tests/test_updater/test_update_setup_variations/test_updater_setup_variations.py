import pytest
from taf.exceptions import UpdateFailedError
from taf.tests.test_updater.update_utils import update_and_check_commit_shas
from taf.updater.types.update import OperationType, UpdateType


@pytest.mark.parametrize(
    "origin_auth_repo",
    [
        {
            "setup_type": "all_files_initially",
            "targets_config": [{"name": "target1"}, {"name": "target2"}],
        },
        {
            "setup_type": "no_info_json",
            "targets_config": [{"name": "target1"}, {"name": "target2"}],
        },
        {
            "setup_type": "mirrors_added_later",
            "targets_config": [{"name": "target1"}, {"name": "target2"}],
        },
        {
            "setup_type": "repositories_and_mirrors_added_later",
            "targets_config": [{"name": "target1"}, {"name": "target2"}],
        },
        {
            "setup_type": "no_target_repositories",
            "targets_config": [{"name": "target1"}, {"name": "target2"}],
        },
        {
            "setup_type": "all_files_initially",
            "targets_config": [{"name": "target1"}, {"name": "target2"}],
            "is_test_repo": True,
        },
    ],
    indirect=True,
)
def test_clone_expect_valid(origin_auth_repo, client_dir):
    is_test_repo = origin_auth_repo.is_test_repo
    expected_repo_type = UpdateType.TEST if is_test_repo else UpdateType.OFFICIAL
    update_and_check_commit_shas(
        OperationType.CLONE,
        None,
        origin_auth_repo,
        client_dir,
        expected_repo_type=expected_repo_type,
    )


@pytest.mark.parametrize(
    "origin_auth_repo",
    [
        {
            "setup_type": "all_files_initially",
            "targets_config": [{"name": "target1"}, {"name": "target2"}],
            "is_test_repo": False,
        },
    ],
    indirect=True,
)
def test_clone_wrong_update_type(origin_auth_repo, client_dir):
    is_test_repo = origin_auth_repo.is_test_repo

    # wrong type
    expected_repo_type = UpdateType.OFFICIAL if is_test_repo else UpdateType.TEST

    with pytest.raises(UpdateFailedError) as exc_info:
        update_and_check_commit_shas(
            OperationType.CLONE,
            None,
            origin_auth_repo,
            client_dir,
            expected_repo_type=expected_repo_type,
        )

        assert "is not a test repository" in str(exc_info.value)
