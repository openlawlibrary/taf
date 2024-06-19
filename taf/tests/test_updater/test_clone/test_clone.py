import pytest
from taf import settings
from taf.auth_repo import AuthenticationRepository
from taf.tests.test_updater.update_utils import check_if_last_validated_commit_exists, update_and_check_commit_shas, update_invalid_repos_and_check_if_repos_exist
from taf.updater.types.update import OperationType

TARGET_MISSMATCH_PATTERN = r"Update of (\w+)\/(\w+) failed due to error: Failure to validate (\w+)\/(\w+) commit ([0-9a-f]{40}) committed on (\d{4}-\d{2}-\d{2}): data repository ([\w\/-]+) was supposed to be at commit ([0-9a-z]{40}) but repo was at ([0-9a-f]{40})"
TARGET_ADDITIONAL_COMMIT_PATTERN =TARGET_ADDITIONAL_COMMIT_PATTERN = r"Update of (\w+)\/(\w+) failed due to error: Failure to validate (\w+)\/(\w+) commit ([0-9a-f]{40}) committed on (\d{4}-\d{2}-\d{2}): data repository ([\w\/-]+) was supposed to be at commit ([0-9a-f]{40}) but commit not on branch (\w+)"
TARGET_COMMIT_AFTER_LAST_VALIDATED_PATTERN = r"Update of (\w+)\/(\w+) failed due to error: Target repository ([\w\/-]+) does not allow unauthenticated commits, but contains commit\(s\) ([0-9a-f]{40}(?:, [0-9a-f]{40})*) on branch (\w+)"
TARGET_MISSING_COMMIT_PATTERN = r"Update of (\w+)/(\w+) failed due to error: Failure to validate (\w+)/(\w+) commit ([0-9a-f]{40}) committed on (\d{4}-\d{2}-\d{2}): data repository ([\w\/-]+) was supposed to be at commit ([0-9a-f]{40}) but commit not on branch (\w+)"
NOT_CLEAN_PATTERN = r"^Update of ([\w/]+) failed due to error: Repository ([\w/-]+) should contain only committed changes\."
INVALID_KEYS_PATTERN = r"^Update of (\w+)\/(\w+) failed due to error: Validation of authentication repository (\w+)/(\w+) failed at revision ([0-9a-f]{40}) due to error: ([\w/-]+) was signed by (\d+)/(\d+) keys$"
INVALID_METADATA_PATTERN = r"^Update of (\w+)\/(\w+) failed due to error: Validation of authentication repository (\w+)/(\w+) failed at revision ([0-9a-f]{40}) due to error: Invalid metadata file ([\w/]+\.\w+)$"

def setup_module(module):
    settings.update_from_filesystem = True


def teardown_module(module):
    settings.update_from_filesystem = False


# @pytest.mark.parametrize(
#     "origin_auth_repo",
#     [
#         {
#             "targets_config": [{"name": "target1"}, {"name": "target2"}],
#             "update_instructions": [
#                 {"action": "add_valid_target_commits"},
#             ],
#             "description": "Setup repository and create and sign additional target commits",
#         },
#         {
#             "targets_config": [
#                 {"name": "target1"},
#                 {"name": "target2", "allow_unauthenticated_commits": True},
#             ],
#             "update_instructions": [
#                 {"action": "add_unauthenticated_commits"},
#                 {"action": "add_valid_target_commits"},
#                 {"action": "add_unauthenticated_commits"},
#             ],
#             "description": "Setup repository and add unauthenticated commits",
#         },
#         {
#             "is_test_repo": True,
#             "targets_config": [{"name": "target1"}, {"name": "target2"}],
#             "update_instructions": [
#                 {"action": "add_valid_target_commits"},
#             ],
#             "description": "Test clone when the repository is a test repository",
#         },
#         {
#             "targets_config": [{"name": "target1"}, {"name": "target2"}],
#             "update_instructions": [
#                 {"action": "update_expiration_dates"},
#             ],
#             "description": "Setup repository and add an additional auth commit",
#         },
#         {
#             "date": "2020-01-01",
#             "targets_config": [{"name": "target1"}, {"name": "target2"}],
#             "update_instructions": [
#                 {
#                     "action": "update_expiration_dates",
#                     "params": {"date": "2021-01-01"},
#                 },
#             ],
#             "description": "Test clone with expired metadata. Expect successful clone without --strict flag",
#         },
#         {
#             "targets_config": [{"name": "target1"}, {"name": "target2"}],
#             "update_instructions": [
#                 {
#                     "action": "create_new_target_orphan_branches",
#                     "params": {"branch_name": "branch1"},
#                 },
#                 {"action": "add_valid_target_commits"},
#             ],
#             "description": "Test clone when target commits contain multiple branches",
#         },
#         {
#             "targets_config": [{"name": "target1"}, {"name": "target2"}],
#             "update_instructions": [
#                 {"action": "update_expiration_dates", "params": {"roles": ["root"]}},
#             ],
#             "description": "Setup repository and add an additional auth commit which updates the root metadata",
#         },
#         {
#             "targets_config": [{"name": "target1"}, {"name": "target2"}],
#             "update_instructions": [
#                 {
#                     "action": "update_role_metadata_without_signing",
#                     "params": {"role": "root"},
#                 },
#                 {
#                     "action": "update_and_sign_metadata_without_clean_check",
#                     "params": {"roles": ["root"]},
#                 },
#             ],
#             "description": "Setup repository and add a commit which updates the root metadata, but skips one version (from 1 to 3).",
#         },
#     ],
#     indirect=True,
# )
# def test_clone_valid(origin_auth_repo, client_dir):
#     is_test_repo = origin_auth_repo.is_test_repo
#     expected_repo_type = UpdateType.TEST if is_test_repo else UpdateType.OFFICIAL
#     update_and_check_commit_shas(
#         OperationType.CLONE,
#         origin_auth_repo,
#         client_dir,
#         expected_repo_type=expected_repo_type,
#     )


# @pytest.mark.parametrize(
#     "origin_auth_repo, excluded_target_globs",
#     [
#         (
#             {
#                 "targets_config": [{"name": "target1"}, {"name": "target2"}],
#             },
#             ["*/target1"],
#         )
#     ],
#     indirect=True,
# )
# def test_excluded_targets_update_no_client_repo(
#     origin_auth_repo,
#     excluded_target_globs,
#     client_dir,
# ):
#     is_test_repo = origin_auth_repo.is_test_repo
#     expected_repo_type = UpdateType.TEST if is_test_repo else UpdateType.OFFICIAL
#     update_and_check_commit_shas(
#         OperationType.CLONE,
#         origin_auth_repo,
#         client_dir,
#         expected_repo_type=expected_repo_type,
#         excluded_target_globs=excluded_target_globs,
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
#     ],
#     indirect=["origin_auth_repo"],
# )
# def test_valid_update_no_(\w+)_target_repo_exists(
#     origin_auth_repo, existing_target_repositories, client_dir
# ):
#     for existing_repository in existing_target_repositories:
#         repo_name = f"{origin_auth_repo.name.split('/')[0]}/{existing_repository}"
#         client_repo = clone_client_repo(
#             repo_name, origin_auth_repo.path.parent.parent, client_dir
#         )
#         assert client_repo.path.is_dir()

#     is_test_repo = origin_auth_repo.is_test_repo
#     expected_repo_type = UpdateType.TEST if is_test_repo else UpdateType.OFFICIAL
#     update_and_check_commit_shas(
#         OperationType.CLONE,
#         origin_auth_repo,
#         client_dir,
#         expected_repo_type=expected_repo_type,
#     )



@pytest.mark.parametrize(
    "origin_auth_repo, expected_error_pattern",
    [
        (
            {
                "targets_config": [{"name": "target1"}, {"name": "target2"}],
                "update_instructions": [
                    {"action": "add_unauthenticated_commits", "params": {"include_all_repos": True}},
                ],
                "description": "Setup repository and create and sign additional target commits",
            },
            TARGET_COMMIT_AFTER_LAST_VALIDATED_PATTERN
        )
    ],
    indirect=["origin_auth_repo"],
)
def test_clone_invalid_expect_partial_update(
    origin_auth_repo, expected_error_pattern, client_dir
):

    update_invalid_repos_and_check_if_repos_exist(
        OperationType.CLONE,
        origin_auth_repo,
        client_dir,
        expected_error_pattern,
        True,
    )
    client_auth_repo = AuthenticationRepository(client_dir, origin_auth_repo.name)
    # make sure that the last validated commit does not exist
    check_if_last_validated_commit_exists(
        client_auth_repo, True
    )


# @pytest.mark.parametrize(
#     "test_name, expected_error, (\w+)_name_exists, expect_partial_update, should_last_validated_exist",
#     [
#         ("test-updater-invalid-target-sha", TARGET_MISSMATCH_PATTERN, True, True, True),
#         (
#             "test-updater-additional-target-commit",
#             TARGET_COMMIT_AFTER_LAST_VALIDATED_PATTERN,
#             True,
#             True,
#             True,
#         ),
#         # TODO: re-enable when old-snapshot validation is fully supported
#         # Issue: https://github.com/openlawlibrary/taf/issues/385
#         # (
#         #     "test-updater-updated-root-old-snapshot",
#         #     INVALID_METADATA_PATTERN,
#         #     True,
#         #     False,
#         #     False,
#         # ),
#         (
#             "test-updater-missing-target-commit",
#             TARGET_ADDITIONAL_COMMIT_PATTERN,
#             True,
#             True,
#             True,
#         ),
#         ("test-updater-wrong-key", INVALID_KEYS_PATTERN, True, True, True),
#         ("test-updater-invalid-version-number", REPLAYED_METADATA, True, True, True),
#         (
#             "test-updater-delegated-roles-wrong-sha",
#             TARGET_MISSMATCH_PATTERN,
#             True,
#             True,
#             True,
#         ),
#         (
#             "test-updater-updated-root-invalid-metadata",
#             INVALID_KEYS_PATTERN,
#             True,
#             True,
#             True,
#         ),
#         ("test-updater-info-missing", NO_REPOSITORY_INFO_JSON, False, True, False),
#         (
#             "test-updater-invalid-snapshot-meta-field-missing",
#             METADATA_FIELD_MISSING,
#             False,
#             True,
#             True,
#         ),
#     ],
# )
# def test_updater_invalid_update(
#     test_name,
#     expected_error,
#     (\w+)_name_exists,
#     updater_repositories,
#     client_dir,
#     expect_partial_update,
#     should_last_validated_exist,
# ):
#     repositories = updater_repositories[test_name]
#     clients_(\w+)_path = client_dir / AUTH_REPO_REL_PATH

#     _update_invalid_repos_and_check_if_repos_exist(
#         OperationType.CLONE,
#         client_dir,
#         repositories,
#         expected_error,
#         expect_partial_update,
#         (\w+)_name_exists=(\w+)_name_exists,
#     )
#     # make sure that the last validated commit does not exist
#     _check_if_last_validated_commit_exists(
#         clients_(\w+)_path, should_last_validated_exist
#     )
