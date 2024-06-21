import pytest
from taf.tests.test_updater.conftest import SetupState
from taf.tests.test_updater.update_utils import update_and_check_commit_shas
from taf.updater.types.update import OperationType, UpdateType


@pytest.mark.parametrize(
    "origin_auth_repo",
    [
        {
            "setup_type": SetupState.ALL_FILES_INITIALLY,
            "targets_config": [{"name": "target1"}, {"name": "target2"}],
        },
        {
            "setup_type": SetupState.NO_INFO_JSON,
            "targets_config": [{"name": "target1"}, {"name": "target2"}],
        },
        {
            "setup_type": SetupState.MIRRORS_ADDED_LATER,
            "targets_config": [{"name": "target1"}, {"name": "target2"}],
        },
        {
            "setup_type": SetupState.MIRRORS_AND_REPOSITOIRES_ADDED_LATER,
            "targets_config": [{"name": "target1"}, {"name": "target2"}],
        },
        {
            "setup_type": SetupState.NO_TARGET_REPOSITORIES,
            "targets_config": [{"name": "target1"}, {"name": "target2"}],
        },
        {
            "setup_type": SetupState.ALL_FILES_INITIALLY,
            "targets_config": [{"name": "target1"}, {"name": "target2"}],
            "is_test_repo": True,
        },
    ],
    indirect=True,
)
def test_clone_expect_valid(origin_auth_repo, client_dir):
    update_and_check_commit_shas(
        OperationType.CLONE,
        origin_auth_repo,
        client_dir,
        expected_repo_type=UpdateType.EITHER,
    )
