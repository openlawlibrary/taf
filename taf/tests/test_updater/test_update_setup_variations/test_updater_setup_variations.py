from taf.log import disable_console_logging, disable_file_logging
import pytest
from taf import settings
from taf.tests.test_updater.update_utils import update_and_check_commit_shas
from taf.updater.types.update import OperationType, UpdateType


disable_console_logging()
disable_file_logging()


def setup_module(module):
    settings.update_from_filesystem = True


def teardown_module(module):
    settings.update_from_filesystem = False


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
    update_and_check_commit_shas(
        OperationType.CLONE,
        origin_auth_repo,
        client_dir,
        expected_repo_type=UpdateType.EITHER,
    )
