import pytest
from taf.tests.test_updater.conftest import apply_update_instructions
from taf.tests.test_updater.update_utils import (
    clone_repositories,
    update_and_check_commit_shas,
)
from taf.updater.types.update import OperationType, UpdateType


@pytest.mark.parametrize(
    "origin_auth_repo_and_targets, update_instructions",
    [
        (
            {
                "targets_config": [{"name": "target1"}, {"name": "target2"}],
            },
            {
                "instructions": [
                    {"action": "add_valid_target_commits"},
                ],
                "description": "Setup repository and create and sign additional target commits",
            },
        ),
        (
            {
                "targets_config": [
                    {"name": "target1"},
                    {"name": "target2", "allow_unauthenticated_commits": True},
                ],
            },
            {
                "instructions": [
                    {"action": "add_unauthenticated_commits"},
                    {"action": "add_valid_target_commits"},
                    {"action": "add_unauthenticated_commits"},
                ],
                "description": "Setup repository and add unauthenticated commits",
            },
        ),
        (
            {
                "is_test_repo": True,
                "targets_config": [{"name": "target1"}, {"name": "target2"}],
            },
            {
                "instructions": [
                    {"action": "add_valid_target_commits"},
                ],
                "description": "Test clone when the repository is a test repository",
            },
        ),
        (
            {
                "targets_config": [{"name": "target1"}, {"name": "target2"}],
            },
            {
                "instructions": [
                    {"action": "update_expiration_dates"},
                ],
                "description": "Setup repository and add an additional auth commit",
            },
        ),
        (
            {
                "date": "2020-01-01",
                "targets_config": [{"name": "target1"}, {"name": "target2"}],
            },
            {
                "instructions": [
                    {
                        "action": "update_expiration_dates",
                        "params": {"date": "2021-01-01"},
                    },
                ],
                "description": "Test clone with expired metadata. Expect successful clone without --strict flag",
            },
        ),
        (
            {
                "targets_config": [{"name": "target1"}, {"name": "target2"}],
            },
            {
                "instructions": [
                    {
                        "action": "create_new_target_orphan_branches",
                        "params": {"branch_name": "branch1"},
                    },
                    {"action": "add_valid_target_commits"},
                ],
                "description": "Test clone when target commits contain multiple branches",
            },
        ),
        (
            {
                "targets_config": [{"name": "target1"}, {"name": "target2"}],
            },
            {
                "instructions": [
                    {
                        "action": "update_expiration_dates",
                        "params": {"roles": ["root"]},
                    },
                ],
                "description": "Setup repository and add an additional auth commit which updates the root metadata",
            },
        ),
        (
            {
                "targets_config": [{"name": "target1"}, {"name": "target2"}],
            },
            {
                "instructions": [
                    {
                        "action": "update_role_metadata_without_signing",
                        "params": {"role": "root"},
                    },
                    {
                        "action": "update_and_sign_metadata_without_clean_check",
                        "params": {"roles": ["root"]},
                    },
                ],
                "description": "Setup repository and add a commit which updates the root metadata, but skips one version (from 1 to 3).",
            },
        ),
    ],
    indirect=True,
)
def test_update_valid(origin_auth_repo_and_targets, update_instructions, client_dir):
    origin_auth_repo, targets_config = origin_auth_repo_and_targets
    is_test_repo = origin_auth_repo.is_test_repo
    expected_repo_type = UpdateType.TEST if is_test_repo else UpdateType.OFFICIAL
    clone_repositories(
        origin_auth_repo,
        client_dir,
        expected_repo_type=expected_repo_type,
    )
    apply_update_instructions(origin_auth_repo, update_instructions, targets_config)
    update_and_check_commit_shas(
        OperationType.UPDATE,
        None,
        origin_auth_repo,
        client_dir,
        expected_repo_type=expected_repo_type,
    )


@pytest.mark.parametrize(
    "origin_auth_repo_and_targets, update_instructions",
    [
        (
            {
                "targets_config": [{"name": "target1"}, {"name": "target2"}],
            },
            {
                "instructions": [
                    {"action": "add_valid_target_commits"},
                ],
                "description": "Setup repository and create and sign additional target commits",
            },
        ),
    ],
    indirect=True,
)
def test_update_when_no_update_necessary(
    origin_auth_repo_and_targets, update_instructions, client_dir
):
    origin_auth_repo, targets_config = origin_auth_repo_and_targets
    is_test_repo = origin_auth_repo.is_test_repo
    expected_repo_type = UpdateType.TEST if is_test_repo else UpdateType.OFFICIAL
    apply_update_instructions(origin_auth_repo, update_instructions, targets_config)
    clone_repositories(
        origin_auth_repo,
        client_dir,
        expected_repo_type=expected_repo_type,
    )
    update_and_check_commit_shas(
        OperationType.UPDATE,
        None,
        origin_auth_repo,
        client_dir,
        expected_repo_type=expected_repo_type,
    )
