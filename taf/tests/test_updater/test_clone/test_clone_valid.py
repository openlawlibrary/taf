import pytest
from taf.tests.test_updater.conftest import (
    SetupManager,
    add_unauthenticated_commit_to_target_repo,
    add_unauthenticated_commits_to_all_target_repos,
    add_valid_target_commits,
    add_valid_unauthenticated_commits,
    clone_client_repo,
    create_new_target_orphan_branches,
    update_and_sign_metadata_without_clean_check,
    update_expiration_dates,
    update_role_metadata_without_signing,
    cleanup_directory,
)
from taf.tests.test_updater.update_utils import (
    clone_client_target_repos_without_updater,
    update_and_check_commit_shas,
    verify_repos_exist,
)
from taf.updater.types.update import OperationType, UpdateType


@pytest.mark.parametrize(
    "origin_auth_repo",
    [
        {
            "targets_config": [{"name": "target1"}, {"name": "target2"}],
        },
        {
            "is_test_repo": True,
            "targets_config": [{"name": "target1"}, {"name": "target2"}],
        },
    ],
    indirect=True,
)
def test_clone_valid_happy_path(origin_auth_repo, client_dir):

    setup_manager = SetupManager(origin_auth_repo)
    setup_manager.add_task(add_valid_target_commits)
    setup_manager.execute_tasks()

    is_test_repo = origin_auth_repo.is_test_repo
    expected_repo_type = UpdateType.TEST if is_test_repo else UpdateType.OFFICIAL
    update_and_check_commit_shas(
        OperationType.CLONE,
        origin_auth_repo,
        client_dir,
        expected_repo_type=expected_repo_type,
    )
    cleanup_directory(client_dir)


@pytest.mark.parametrize(
    "origin_auth_repo",
    [
        {
            "targets_config": [{"name": "target1"}, {"name": "target2"}],
        },
        {
            "is_test_repo": True,
            "targets_config": [{"name": "target1"}, {"name": "target2"}],
        },
    ],
    indirect=True,
)
def test_clone_valid_happy_path_bare_flag(origin_auth_repo, client_dir):

    setup_manager = SetupManager(origin_auth_repo)
    setup_manager.add_task(add_valid_target_commits)
    setup_manager.execute_tasks()

    is_test_repo = origin_auth_repo.is_test_repo
    expected_repo_type = UpdateType.TEST if is_test_repo else UpdateType.OFFICIAL
    update_and_check_commit_shas(
        OperationType.CLONE,
        origin_auth_repo,
        client_dir,
        expected_repo_type=expected_repo_type,
        bare=True,
    )


@pytest.mark.parametrize(
    "origin_auth_repo",
    [
        {
            "targets_config": [
                {"name": "target1", "allow_unauthenticated_commits": True},
                {"name": "target2", "allow_unauthenticated_commits": True},
            ],
        },
        {
            "targets_config": [
                {"name": "target1"},
                {"name": "target2", "allow_unauthenticated_commits": True},
            ],
        },
    ],
    indirect=True,
)
def test_clone_valid_with_unauthenticated_commits(origin_auth_repo, client_dir):

    setup_manager = SetupManager(origin_auth_repo)
    setup_manager.add_task(add_valid_unauthenticated_commits)
    setup_manager.add_task(add_valid_target_commits)
    setup_manager.add_task(add_valid_unauthenticated_commits)
    setup_manager.execute_tasks()

    update_and_check_commit_shas(
        OperationType.CLONE,
        origin_auth_repo,
        client_dir,
        expected_repo_type=UpdateType.OFFICIAL,
    )


@pytest.mark.parametrize(
    "origin_auth_repo",
    [
        {
            "targets_config": [{"name": "target1"}, {"name": "target2"}],
        },
    ],
    indirect=True,
)
def test_clone_valid_when_updated_expiration_dates(origin_auth_repo, client_dir):
    setup_manager = SetupManager(origin_auth_repo)
    setup_manager.add_task(update_expiration_dates)
    setup_manager.execute_tasks()

    update_and_check_commit_shas(
        OperationType.CLONE,
        origin_auth_repo,
        client_dir,
        expected_repo_type=UpdateType.EITHER,
    )


@pytest.mark.parametrize(
    "origin_auth_repo",
    [
        {
            "date": "2020-01-01",
            "targets_config": [{"name": "target1"}, {"name": "target2"}],
        },
    ],
    indirect=True,
)
def test_clone_valid_when_expired_metadata_no_strict_flag(origin_auth_repo, client_dir):
    setup_manager = SetupManager(origin_auth_repo)
    setup_manager.add_task(update_expiration_dates, kwargs={"date": "2021-01-01"})
    setup_manager.execute_tasks()

    update_and_check_commit_shas(
        OperationType.CLONE,
        origin_auth_repo,
        client_dir,
        expected_repo_type=UpdateType.EITHER,
    )


@pytest.mark.parametrize(
    "origin_auth_repo",
    [{"targets_config": [{"name": "target1"}, {"name": "target2"}]}],
    indirect=True,
)
def test_clone_valid_when_multiple_branches(origin_auth_repo, client_dir):
    setup_manager = SetupManager(origin_auth_repo)
    setup_manager.add_task(
        create_new_target_orphan_branches, kwargs={"branch_name": "branch1"}
    )
    setup_manager.execute_tasks()

    update_and_check_commit_shas(
        OperationType.CLONE,
        origin_auth_repo,
        client_dir,
        expected_repo_type=UpdateType.EITHER,
    )


@pytest.mark.parametrize(
    "origin_auth_repo",
    [{"targets_config": [{"name": "target1"}, {"name": "target2"}]}],
    indirect=True,
)
def test_clone_valid_when_only_root_metadata_updated(origin_auth_repo, client_dir):
    setup_manager = SetupManager(origin_auth_repo)
    setup_manager.add_task(update_expiration_dates, kwargs={"roles": ["root"]})
    setup_manager.execute_tasks()

    update_and_check_commit_shas(
        OperationType.CLONE,
        origin_auth_repo,
        client_dir,
        expected_repo_type=UpdateType.EITHER,
    )


@pytest.mark.parametrize(
    "origin_auth_repo",
    [{"targets_config": [{"name": "target1"}, {"name": "target2"}]}],
    indirect=True,
)
def test_clone_valid_when_root_version_skipped(origin_auth_repo, client_dir):
    setup_manager = SetupManager(origin_auth_repo)
    setup_manager.add_task(
        update_role_metadata_without_signing, kwargs={"role": "root"}
    )
    setup_manager.add_task(
        update_and_sign_metadata_without_clean_check, kwargs={"roles": ["root"]}
    )
    setup_manager.execute_tasks()

    update_and_check_commit_shas(
        OperationType.CLONE,
        origin_auth_repo,
        client_dir,
        expected_repo_type=UpdateType.EITHER,
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
    indirect=["origin_auth_repo"],
)
def test_valid_clone_when_exclude_target(
    origin_auth_repo,
    excluded_target_globs,
    client_dir,
):
    update_and_check_commit_shas(
        OperationType.CLONE,
        origin_auth_repo,
        client_dir,
        expected_repo_type=UpdateType.EITHER,
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
    indirect=["origin_auth_repo"],
)
def test_valid_update_when_target_repo_exists(
    origin_auth_repo, existing_target_repositories, client_dir
):
    for existing_repository in existing_target_repositories:
        repo_name = f"{origin_auth_repo.name.split('/')[0]}/{existing_repository}"
        client_repo = clone_client_repo(
            repo_name, origin_auth_repo.path.parent.parent, client_dir
        )
        assert client_repo.path.is_dir()

    update_and_check_commit_shas(
        OperationType.CLONE,
        origin_auth_repo,
        client_dir,
        expected_repo_type=UpdateType.EITHER,
    )


@pytest.mark.parametrize(
    "origin_auth_repo",
    [
        {
            "targets_config": [{"name": "target1"}, {"name": "target2"}],
        },
    ],
    indirect=True,
)
def test_clone_when_targets_exist_not_auth_repo(origin_auth_repo, client_dir):
    clone_client_target_repos_without_updater(origin_auth_repo, client_dir)

    update_and_check_commit_shas(
        OperationType.CLONE,
        origin_auth_repo,
        client_dir,
        expected_repo_type=UpdateType.EITHER,
    )


@pytest.mark.parametrize(
    "origin_auth_repo",
    [
        {
            "targets_config": [{"name": "target1"}, {"name": "target2"}],
        },
    ],
    indirect=True,
)
def test_clone_valid_when_no_upstream_top_commits_unsigned(
    origin_auth_repo, client_dir
):

    setup_manager = SetupManager(origin_auth_repo)
    setup_manager.add_task(add_unauthenticated_commits_to_all_target_repos)
    setup_manager.execute_tasks()

    update_and_check_commit_shas(
        OperationType.CLONE,
        origin_auth_repo,
        client_dir,
        expected_repo_type=UpdateType.EITHER,
        no_upstream=True,
    )


@pytest.mark.parametrize(
    "origin_auth_repo",
    [
        {
            "targets_config": [
                {"name": "notempty"},
                {"name": "empty", "is_empty": True},
            ],
        },
    ],
    indirect=True,
)
def test_clone_when_target_empty(origin_auth_repo, client_dir):

    update_and_check_commit_shas(
        OperationType.CLONE,
        origin_auth_repo,
        client_dir,
        expected_repo_type=UpdateType.EITHER,
    )
    verify_repos_exist(client_dir, origin_auth_repo, excluded=["empty"])


@pytest.mark.parametrize(
    "origin_auth_repo",
    [
        {
            "targets_config": [
                {"name": "target1"},
                {"name": "target2", "is_empty": True},
            ],
        },
    ],
    indirect=True,
)
def test_clone_when_no_target_file_and_commit(origin_auth_repo, client_dir):

    setup_manager = SetupManager(origin_auth_repo)
    setup_manager.add_task(
        add_unauthenticated_commit_to_target_repo, kwargs={"target_name": "target2"}
    )
    setup_manager.execute_tasks()

    update_and_check_commit_shas(
        OperationType.CLONE,
        origin_auth_repo,
        client_dir,
        expected_repo_type=UpdateType.EITHER,
    )
    verify_repos_exist(client_dir, origin_auth_repo, excluded=["target2"])
