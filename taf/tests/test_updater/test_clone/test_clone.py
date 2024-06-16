import pytest
from taf.tests.test_updater.update_utils import update_and_check_commit_shas
from taf.updater.types.update import OperationType, UpdateType


@pytest.mark.parametrize(
    "origin_auth_repo",
    [
        {
            "targets_config": [{"name": "target1"}, {"name": "target2"}],
            "update_instructions": [
                {"action": "add_valid_target_commits"},
            ],
        },
        {
            "targets_config": [
                {"name": "target1"},
                {"name": "target2", "allow_unauthenticated_commits": True},
            ],
            "update_instructions": [
                {"action": "add_unauthenticated_commits"},
                {"action": "add_valid_target_commits"},
                {"action": "add_unauthenticated_commits"},
            ],
        },
        {
            "is_test_repo": True,
            "targets_config": [{"name": "target1"}, {"name": "target2"}],
            "update_instructions": [
                {"action": "add_valid_target_commits"},
            ],
        },
        {
            "targets_config": [{"name": "target1"}, {"name": "target2"}],
            "update_instructions": [
                {"action": "update_expiration_dates"},
            ],
        },
        {
            "date": "2020-01-01",
            "targets_config": [{"name": "target1"}, {"name": "target2"}],
            "update_instructions": [
                {
                    "action": "update_expiration_dates",
                    "params": {"datea": "2021-01-01"},
                },
            ],
        },
        {
            "targets_config": [{"name": "target1"}, {"name": "target2"}],
            "update_instructions": [
                {
                    "action": "create_new_target_orphan_branches",
                    "params": {"branch_name": "branch1"},
                },
                {"action": "add_valid_target_commits"},
            ],
        },
        {
            "targets_config": [{"name": "target1"}, {"name": "target2"}],
            "update_instructions": [
                {"action": "update_expiration_dates", "params": {"roles": ["root"]}},
            ],
        },
        {
            "targets_config": [{"name": "target1"}, {"name": "target2"}],
            "update_instructions": [
                {
                    "action": "update_role_metadata_without_signing",
                    "params": {"role": "root"},
                },
                {
                    "action": "update_and_sign_metadata_without_clean_check",
                    "params": {"roles": ["root"]},
                },
            ],
        },
    ],
    indirect=True,
)
def test_clone_valid(origin_auth_repo, client_dir):
    is_test_repo = origin_auth_repo.is_test_repo
    expected_repo_type = UpdateType.TEST if is_test_repo else UpdateType.OFFICIAL
    update_and_check_commit_shas(
        OperationType.CLONE,
        None,
        origin_auth_repo,
        client_dir,
        expected_repo_type=expected_repo_type,
    )
