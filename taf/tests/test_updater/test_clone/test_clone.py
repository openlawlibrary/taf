import pytest
from taf.tests.test_updater.conftest import clone_client_repo
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
            "description": "Setup repository and create and sign additional target commits",
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
            "description": "Setup repository and add unauthenticated commits",
        },
        {
            "is_test_repo": True,
            "targets_config": [{"name": "target1"}, {"name": "target2"}],
            "update_instructions": [
                {"action": "add_valid_target_commits"},
            ],
            "description": "Test clone when the repository is a test repository",
        },
        {
            "targets_config": [{"name": "target1"}, {"name": "target2"}],
            "update_instructions": [
                {"action": "update_expiration_dates"},
            ],
            "description": "Setup repository and add an additional auth commit",
        },
        {
            "date": "2020-01-01",
            "targets_config": [{"name": "target1"}, {"name": "target2"}],
            "update_instructions": [
                {
                    "action": "update_expiration_dates",
                    "params": {"date": "2021-01-01"},
                },
            ],
            "description": "Test clone with expired metadata. Expect successful clone without --strict flag",
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
            "description": "Test clone when target commits contain multiple branches",
        },
        {
            "targets_config": [{"name": "target1"}, {"name": "target2"}],
            "update_instructions": [
                {"action": "update_expiration_dates", "params": {"roles": ["root"]}},
            ],
            "description": "Setup repository and add an additional auth commit which updates the root metadata",
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
            "description": "Setup repository and add a commit which updates the root metadata, but skips one version (from 1 to 3).",
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


@pytest.mark.parametrize(
    "origin_auth_repo, excluded_target_globs",
    [
        (
            {
                "targets_config": [{"name": "target1"}, {"name": "target2"}],
            },
            ["*/target1"],
        )
    ],
    indirect=True,
)
def test_excluded_targets_update_no_client_repo(
    origin_auth_repo,
    excluded_target_globs,
    client_dir,
):
    is_test_repo = origin_auth_repo.is_test_repo
    expected_repo_type = UpdateType.TEST if is_test_repo else UpdateType.OFFICIAL
    update_and_check_commit_shas(
        OperationType.CLONE,
        None,
        origin_auth_repo,
        client_dir,
        expected_repo_type=expected_repo_type,
        excluded_target_globs=excluded_target_globs,
    )


@pytest.mark.parametrize(
    "origin_auth_repo, existing_target_repositories",
    [
        (
            {
                "targets_config": [{"name": "target1"}, {"name": "target2"}],
            },
            ["target1"],
        ),
    ],
    indirect=True,
)
def test_valid_update_no_auth_repo_target_repo_exists(
    origin_auth_repo, existing_target_repositories, client_dir
):
    for existing_repository in existing_target_repositories:
        repo_name = f"{origin_auth_repo.name.split('/')[0]}/{existing_repository}"
        client_repo = clone_client_repo(
            repo_name, origin_auth_repo.path.parent.parent, client_dir
        )
        assert client_repo.path.is_dir()

    is_test_repo = origin_auth_repo.is_test_repo
    expected_repo_type = UpdateType.TEST if is_test_repo else UpdateType.OFFICIAL
    update_and_check_commit_shas(
        OperationType.CLONE,
        None,
        origin_auth_repo,
        client_dir,
        expected_repo_type=expected_repo_type,
    )
