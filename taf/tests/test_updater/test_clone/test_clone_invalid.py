
import pytest
from taf import settings
from taf.auth_repo import AuthenticationRepository
from taf.tests.test_updater.conftest import SetupManager, add_unauthenticated_commits_to_all_target_repos, add_valid_target_commits, add_valid_unauthenticated_commits, clone_client_repo, create_new_target_orphan_branches, swap_last_two_commits, update_and_sign_metadata_without_clean_check, update_expiration_dates, update_role_metadata_invalid_signature, update_role_metadata_without_signing
from taf.tests.test_updater.update_utils import check_if_last_validated_commit_exists, update_and_check_commit_shas, update_invalid_repos_and_check_if_repos_exist
from taf.updater.types.update import OperationType, UpdateType

TARGET_MISSMATCH_PATTERN = r"Update of (\w+)\/(\w+) failed due to error: Failure to validate (\w+)\/(\w+) commit ([0-9a-f]{40}) committed on (\d{4}-\d{2}-\d{2}): data repository ([\w\/-]+) was supposed to be at commit ([0-9a-z]{40}) but repo was at ([0-9a-f]{40})"
TARGET_ADDITIONAL_COMMIT_PATTERN =TARGET_ADDITIONAL_COMMIT_PATTERN = r"Update of (\w+)\/(\w+) failed due to error: Failure to validate (\w+)\/(\w+) commit ([0-9a-f]{40}) committed on (\d{4}-\d{2}-\d{2}): data repository ([\w\/-]+) was supposed to be at commit ([0-9a-f]{40}) but commit not on branch (\w+)"
TARGET_COMMIT_AFTER_LAST_VALIDATED_PATTERN = r"Update of (\w+)\/(\w+) failed due to error: Target repository ([\w\/-]+) does not allow unauthenticated commits, but contains commit\(s\) ([0-9a-f]{40}(?:, [0-9a-f]{40})*) on branch (\w+)"
TARGET_MISSING_COMMIT_PATTERN = r"Update of (\w+)/(\w+) failed due to error: Failure to validate (\w+)/(\w+) commit ([0-9a-f]{40}) committed on (\d{4}-\d{2}-\d{2}): data repository ([\w\/-]+) was supposed to be at commit ([0-9a-f]{40}) but commit not on branch (\w+)"
NOT_CLEAN_PATTERN = r"^Update of ([\w/]+) failed due to error: Repository ([\w/-]+) should contain only committed changes\."
INVALID_KEYS_PATTERN = r"^Update of (\w+)\/(\w+) failed due to error: Validation of authentication repository (\w+)/(\w+) failed at revision ([0-9a-f]{40}) due to error: ([\w/-]+) was signed by (\d+)/(\d+) keys$"
INVALID_METADATA_PATTERN = r"^Update of (\w+)\/(\w+) failed due to error: Validation of authentication repository (\w+)/(\w+) failed at revision ([0-9a-f]{40}) due to error: Invalid metadata file ([\w/]+\.\w+)$"
INVALID_VERSION_NUMBER_PATTERN = r"^Update of (\w+\/\w+) failed due to error: Validation of authentication repository (\w+\/\w+) failed at revision ([0-9a-f]+) due to error: New (\w+) version (\d) must be >= (\d+)$"
WRONG_UPDATE_TYPE_TEST_REPO = r"Update of (\w+\/\w+) failed due to error: Repository (\w+\/\w+) is a test repository. Call update with \"--expected-repo-type\" test to update a test repository$"
WRONG_UPDATE_TYPE_OFFICIAL_REPO = r"Update of (\w+\/\w+) failed due to error: Repository (\w+\/\w+) is not a test repository, but update was called with the \"--expected-repo-type\" test$"
METADATA_EXPIRED =r"Update of (\w+\/\w+) failed due to error: Validation of authentication repository (\w+\/\w+) failed at revision [0-9a-f]+ due to error: .+ is expired"
NO_REPOSITORY_INFO_JSON = "Update of repository failed due to error: Error during info.json parse. If the authentication repository's path is not specified, info.json metadata is expected to be in targets/protected"

def setup_module(module):
    settings.update_from_filesystem = True


def teardown_module(module):
    settings.update_from_filesystem = False

# @pytest.mark.parametrize(
#     "origin_auth_repo",
#     [
#         {
#             "targets_config": [{"name": "target1"}, {"name": "target2"}],
#         },
#     ],
#     indirect=True,
# )
# def test_clone_invalid_target_repositories_top_commits_unsigned(
#     origin_auth_repo, client_dir
# ):

#     setup_manager = SetupManager(origin_auth_repo)
#     setup_manager.add_task(add_unauthenticated_commits_to_all_target_repos)
#     setup_manager.execute_tasks()

#     update_invalid_repos_and_check_if_repos_exist(
#         OperationType.CLONE,
#         origin_auth_repo,
#         client_dir,
#         TARGET_COMMIT_AFTER_LAST_VALIDATED_PATTERN,
#         True,
#     )
#     client_auth_repo = AuthenticationRepository(client_dir, origin_auth_repo.name)
#     # make sure that the last validated commit does not exist
#     check_if_last_validated_commit_exists(
#         client_auth_repo, True
#     )



# @pytest.mark.parametrize(
#     "origin_auth_repo",
#     [
#         {
#             "targets_config": [{"name": "target1"}, {"name": "target2"}],
#         },
#     ],
#     indirect=True,
# )
# def test_clone_invalid_target_repositories_contain_unsigned_commits(
#     origin_auth_repo, client_dir
# ):

#     setup_manager = SetupManager(origin_auth_repo)
#     setup_manager.add_task(add_unauthenticated_commits_to_all_target_repos)
#     setup_manager.add_task(add_valid_target_commits)
#     setup_manager.execute_tasks()

#     update_invalid_repos_and_check_if_repos_exist(
#         OperationType.CLONE,
#         origin_auth_repo,
#         client_dir,
#         TARGET_MISSMATCH_PATTERN,
#         True,
#     )
#     client_auth_repo = AuthenticationRepository(client_dir, origin_auth_repo.name)
#     # make sure that the last validated commit does not exist
#     check_if_last_validated_commit_exists(
#         client_auth_repo, True
#     )


# @pytest.mark.parametrize(
#     "origin_auth_repo",
#         [
#             {
#                 "targets_config": [{"name": "target1"}, {"name": "target2"}],
#             }
#         ],
#     indirect=True
# )
# def test_clone_invalid_target_invalid_metadata(
#     origin_auth_repo, client_dir
# ):

#     setup_manager = SetupManager(origin_auth_repo)
#     setup_manager.add_task(update_expiration_dates, kwargs={"repetitions": 2})
#     setup_manager.add_task(swap_last_two_commits)
#     setup_manager.execute_tasks()

#     update_invalid_repos_and_check_if_repos_exist(
#         OperationType.CLONE,
#         origin_auth_repo,
#         client_dir,
#         INVALID_VERSION_NUMBER_PATTERN,
#         True,
#     )
#     client_auth_repo = AuthenticationRepository(client_dir, origin_auth_repo.name)
#     # make sure that the last validated commit does not exist
#     check_if_last_validated_commit_exists(
#         client_auth_repo, True
#     )


# @pytest.mark.parametrize(
#     "origin_auth_repo, existing_target_repositories",
#     [
#         (
#             {
#                 "targets_config": [{"name": "target1"}, {"name": "target2"}],
#             },
#             ["target1"],
#         ),
#         (
#             {
#                 "targets_config": [{"name": "target1"}, {"name": "target2"}],
#             },
#             ["target1", "target2"],
#         )
#     ],
#     indirect=["origin_auth_repo"],
# )
# def test_clone_invalid_target_repositories_targets_exist(
#     origin_auth_repo, existing_target_repositories, client_dir
# ):

#     setup_manager = SetupManager(origin_auth_repo)
#     setup_manager.add_task(add_unauthenticated_commits_to_all_target_repos)
#     setup_manager.add_task(add_valid_target_commits)
#     setup_manager.execute_tasks()

#     for existing_repository in existing_target_repositories:
#         repo_name = f"{origin_auth_repo.name.split('/')[0]}/{existing_repository}"
#         client_repo = clone_client_repo(
#             repo_name, origin_auth_repo.path.parent.parent, client_dir
#         )
#         assert client_repo.path.is_dir()

#     update_invalid_repos_and_check_if_repos_exist(
#         OperationType.CLONE,
#         origin_auth_repo,
#         client_dir,
#         TARGET_MISSMATCH_PATTERN,
#         True,
#     )
#     client_auth_repo = AuthenticationRepository(client_dir, origin_auth_repo.name)
#     # make sure that the last validated commit does not exist
#     check_if_last_validated_commit_exists(
#         client_auth_repo, True
#     )


# @pytest.mark.parametrize(
#     "origin_auth_repo",
#         [
#             {
#                 "targets_config": [{"name": "target1"}, {"name": "target2"}],
#             }
#         ],
#     indirect=True
# )
# def test_clone_invalid_target_invalid_metadata(
#     origin_auth_repo, client_dir
# ):

#     setup_manager = SetupManager(origin_auth_repo)
#     setup_manager.add_task(update_role_metadata_invalid_signature, kwargs={"role": "timestamp"})
#     setup_manager.execute_tasks()

#     update_invalid_repos_and_check_if_repos_exist(
#         OperationType.CLONE,
#         origin_auth_repo,
#         client_dir,
#         INVALID_KEYS_PATTERN,
#         True,
#     )
#     client_auth_repo = AuthenticationRepository(client_dir, origin_auth_repo.name)
#     # make sure that the last validated commit does not exist
#     check_if_last_validated_commit_exists(
#         client_auth_repo, True
#     )

# @pytest.mark.parametrize(
#     "origin_auth_repo",
#     [
#         {
#             "targets_config": [{"name": "target1"}, {"name": "target2"}],
#             "is_test_repo": False,
#         }
#     ],
#     indirect=True,
# )
# def test_clone_invalid_wrong_update_type_when_official_repo(origin_auth_repo, client_dir):

#     update_invalid_repos_and_check_if_repos_exist(
#         OperationType.CLONE,
#         origin_auth_repo,
#         client_dir,
#         WRONG_UPDATE_TYPE_OFFICIAL_REPO,
#         False,
#         expected_repo_type=UpdateType.TEST

#     )
#     client_auth_repo = AuthenticationRepository(client_dir, origin_auth_repo.name)
#     # make sure that the last validated commit does not exist
#     check_if_last_validated_commit_exists(
#         client_auth_repo, False
#     )

# @pytest.mark.parametrize(
#     "origin_auth_repo",
#     [
#         {
#             "targets_config": [{"name": "target1"}, {"name": "target2"}],
#             "is_test_repo": True,
#         },
#     ],
#     indirect=True,
# )
# def test_clone_invalid_wrong_update_type_when_test_repo(origin_auth_repo, client_dir):
#     update_invalid_repos_and_check_if_repos_exist(
#         OperationType.CLONE,
#         origin_auth_repo,
#         client_dir,
#         WRONG_UPDATE_TYPE_TEST_REPO,
#         False,
#         expected_repo_type=UpdateType.OFFICIAL
#     )
#     client_auth_repo = AuthenticationRepository(client_dir, origin_auth_repo.name)
#     # make sure that the last validated commit does not exist
#     check_if_last_validated_commit_exists(
#         client_auth_repo, False
#     )


# @pytest.mark.parametrize(
#     "origin_auth_repo",
#     [
#         {
#             "date": "2020-01-01",
#             "targets_config": [{"name": "target1"}, {"name": "target2"}],
#         },
#     ],
#     indirect=True
# )
# def test_clone_valid_when_expired_metadata_with_strict_flag(origin_auth_repo, client_dir):
#     setup_manager = SetupManager(origin_auth_repo)
#     setup_manager.add_task(update_expiration_dates, kwargs={"date": "2021-01-01"})
#     setup_manager.execute_tasks()

#     update_invalid_repos_and_check_if_repos_exist(
#         OperationType.CLONE,
#         origin_auth_repo,
#         client_dir,
#         METADATA_EXPIRED,
#         True,
#         strict=True,
#     )
#     client_auth_repo = AuthenticationRepository(client_dir, origin_auth_repo.name)
#     # make sure that the last validated commit does not exist
#     check_if_last_validated_commit_exists(
#         client_auth_repo, True
#     )


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
# #         ("test-updater-info-missing", NO_REPOSITORY_INFO_JSON, False, True, False),
# #         (
# #             "test-updater-invalid-snapshot-meta-field-missing",
# #             METADATA_FIELD_MISSING,
# #             False,
# #             True,
# #             True,
# #         ),
# #     ],
# # )

