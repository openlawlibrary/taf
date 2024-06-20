
import pytest
from taf import settings
from taf.auth_repo import AuthenticationRepository
from taf.tests.test_updater.conftest import TARGET_COMMIT_AFTER_LAST_VALIDATED_PATTERN, TARGET_MISSMATCH_PATTERN, SetupManager, add_unauthenticated_commits_to_all_target_repos, add_valid_target_commits, add_valid_unauthenticated_commits, clone_client_repo, create_new_target_orphan_branches, swap_last_two_commits, update_and_sign_metadata_without_clean_check, update_expiration_dates, update_role_metadata_invalid_signature, update_role_metadata_without_signing
from taf.tests.test_updater.update_utils import check_if_last_validated_commit_exists, clone_repositories, update_and_check_commit_shas, update_invalid_repos_and_check_if_repos_exist
from taf.updater.types.update import OperationType, UpdateType


def setup_module(module):
    settings.update_from_filesystem = True


def teardown_module(module):
    settings.update_from_filesystem = False



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



