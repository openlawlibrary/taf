from pathlib import Path
import pytest
from taf.auth_repo import AuthenticationRepository
from taf.tests.test_updater.conftest import (
    SetupManager,
    add_unauthenticated_commits_to_all_target_repos,
    add_valid_target_commits,
    add_valid_unauthenticated_commits,
    create_new_target_orphan_branches,
    remove_commits,
    remove_last_validated_commit,
    remove_last_validated_data,
    replace_with_old_last_validated_commit_format,
    revert_last_validated_commit,
    update_and_sign_metadata_without_clean_check,
    update_expiration_dates,
    update_role_metadata_without_signing,
)
from taf.tests.test_updater.update_utils import (
    clone_client_auth_repo_without_updater,
    clone_repositories,
    load_target_repositories,
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
    ],
    indirect=True,
)
def test_update_valid_happy_path(origin_auth_repo, client_dir):
    clone_repositories(
        origin_auth_repo,
        client_dir,
    )

    setup_manager = SetupManager(origin_auth_repo)
    setup_manager.add_task(add_valid_target_commits)
    setup_manager.execute_tasks()

    update_and_check_commit_shas(
        OperationType.UPDATE,
        origin_auth_repo,
        client_dir,
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
def test_update_when_old_last_validated_commit(origin_auth_repo, client_dir):
    clone_repositories(
        origin_auth_repo,
        client_dir,
    )

    setup_manager = SetupManager(origin_auth_repo)
    setup_manager.add_task(add_valid_target_commits)
    setup_manager.execute_tasks()

    client_auth_repo = AuthenticationRepository(client_dir, origin_auth_repo.name)
    client_setup_manager = SetupManager(client_auth_repo)
    client_setup_manager.add_task(replace_with_old_last_validated_commit_format)
    client_setup_manager.execute_tasks()

    update_and_check_commit_shas(
        OperationType.UPDATE,
        origin_auth_repo,
        client_dir,
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
def test_update_valid_happy_path_bare_flag(origin_auth_repo, client_dir):
    clone_repositories(
        origin_auth_repo,
        client_dir,
    )

    setup_manager = SetupManager(origin_auth_repo)
    setup_manager.add_task(add_valid_target_commits)
    setup_manager.execute_tasks()

    update_and_check_commit_shas(
        OperationType.UPDATE,
        origin_auth_repo,
        client_dir,
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
def test_update_valid_when_unauthenticated_commits(origin_auth_repo, client_dir):
    clone_repositories(
        origin_auth_repo,
        client_dir,
    )

    setup_manager = SetupManager(origin_auth_repo)
    setup_manager.add_task(add_valid_unauthenticated_commits)
    setup_manager.add_task(add_valid_target_commits)
    setup_manager.add_task(add_valid_unauthenticated_commits)
    setup_manager.execute_tasks()

    update_and_check_commit_shas(
        OperationType.UPDATE,
        origin_auth_repo,
        client_dir,
    )


@pytest.mark.parametrize(
    "origin_auth_repo",
    [
        {
            "is_test_repo": True,
            "targets_config": [{"name": "target1"}, {"name": "target2"}],
        },
    ],
    indirect=True,
)
def test_update_valid_when_test_repository(origin_auth_repo, client_dir):
    clone_repositories(
        origin_auth_repo,
        client_dir,
    )

    setup_manager = SetupManager(origin_auth_repo)
    setup_manager.add_task(add_valid_target_commits)
    setup_manager.execute_tasks()

    update_and_check_commit_shas(
        OperationType.UPDATE,
        origin_auth_repo,
        client_dir,
        expected_repo_type=UpdateType.TEST,
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
def test_update_valid_when_expiration_dates_updated(origin_auth_repo, client_dir):
    clone_repositories(
        origin_auth_repo,
        client_dir,
    )

    setup_manager = SetupManager(origin_auth_repo)
    setup_manager.add_task(update_expiration_dates)
    setup_manager.execute_tasks()

    update_and_check_commit_shas(
        OperationType.UPDATE,
        origin_auth_repo,
        client_dir,
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
def test_update_valid_when_epxirated_metadata_no_strict_flag(
    origin_auth_repo, client_dir
):
    clone_repositories(
        origin_auth_repo,
        client_dir,
    )

    setup_manager = SetupManager(origin_auth_repo)
    setup_manager.add_task(update_expiration_dates, kwargs={"date": "2021-01-01"})
    setup_manager.execute_tasks()

    update_and_check_commit_shas(
        OperationType.UPDATE,
        origin_auth_repo,
        client_dir,
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
def test_update_valid_when_multiple_target_branches(origin_auth_repo, client_dir):
    clone_repositories(
        origin_auth_repo,
        client_dir,
    )

    setup_manager = SetupManager(origin_auth_repo)

    setup_manager.add_task(
        create_new_target_orphan_branches, kwargs={"branch_name": "branch1"}
    )
    setup_manager.add_task(add_valid_target_commits)
    setup_manager.execute_tasks()

    update_and_check_commit_shas(
        OperationType.UPDATE,
        origin_auth_repo,
        client_dir,
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
def test_update_valid_when_update_root_metadata(origin_auth_repo, client_dir):
    clone_repositories(
        origin_auth_repo,
        client_dir,
    )

    setup_manager = SetupManager(origin_auth_repo)
    setup_manager.add_task(update_expiration_dates, kwargs={"roles": ["root"]})
    setup_manager.execute_tasks()

    update_and_check_commit_shas(
        OperationType.UPDATE,
        origin_auth_repo,
        client_dir,
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
def test_update_valid_when_root_version_skipped(origin_auth_repo, client_dir):
    clone_repositories(
        origin_auth_repo,
        client_dir,
    )

    setup_manager = SetupManager(origin_auth_repo)
    setup_manager.add_task(
        update_role_metadata_without_signing, kwargs={"role": "root"}
    )
    setup_manager.add_task(
        update_and_sign_metadata_without_clean_check, kwargs={"roles": ["root"]}
    )
    setup_manager.execute_tasks()

    update_and_check_commit_shas(
        OperationType.UPDATE,
        origin_auth_repo,
        client_dir,
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
def test_update_when_no_update_necessary(origin_auth_repo, client_dir):

    setup_manager = SetupManager(origin_auth_repo)
    setup_manager.add_task(add_valid_target_commits)
    setup_manager.execute_tasks()

    clone_repositories(
        origin_auth_repo,
        client_dir,
    )
    update_and_check_commit_shas(
        OperationType.UPDATE,
        origin_auth_repo,
        client_dir,
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
def test_update_when_auth_repo_exists_no_targets(origin_auth_repo, client_dir):
    clone_client_auth_repo_without_updater(origin_auth_repo, client_dir)

    update_and_check_commit_shas(
        OperationType.UPDATE,
        origin_auth_repo,
        client_dir,
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
def test_update_valid_when_last_validated_commit_deleted(origin_auth_repo, client_dir):
    clone_repositories(
        origin_auth_repo,
        client_dir,
    )

    client_auth_repo = AuthenticationRepository(client_dir, origin_auth_repo.name)
    client_setup_manager = SetupManager(client_auth_repo)
    client_setup_manager.add_task(remove_last_validated_commit)
    client_setup_manager.execute_tasks()
    update_and_check_commit_shas(
        OperationType.UPDATE,
        origin_auth_repo,
        client_dir,
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
def test_update_valid_when_last_validated_commit_reverted(origin_auth_repo, client_dir):
    clone_repositories(
        origin_auth_repo,
        client_dir,
    )

    client_auth_repo = AuthenticationRepository(client_dir, origin_auth_repo.name)
    client_setup_manager = SetupManager(client_auth_repo)
    client_setup_manager.add_task(revert_last_validated_commit)
    client_setup_manager.execute_tasks()

    update_and_check_commit_shas(
        OperationType.UPDATE,
        origin_auth_repo,
        client_dir,
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
def test_update_valid_when_no_upstream_when_contain_unsigned_commits(
    origin_auth_repo, client_dir
):

    clone_repositories(
        origin_auth_repo,
        client_dir,
    )

    setup_manager = SetupManager(origin_auth_repo)
    setup_manager.add_task(add_unauthenticated_commits_to_all_target_repos)
    setup_manager.execute_tasks()

    update_and_check_commit_shas(
        OperationType.UPDATE,
        origin_auth_repo,
        client_dir,
        no_upstream=True,
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
def test_update_with_no_last_validated_commit(origin_auth_repo, client_dir):
    clone_repositories(origin_auth_repo, client_dir)

    client_auth_repo = AuthenticationRepository(client_dir, origin_auth_repo.name)
    last_validated_commit_file = (
        Path(client_auth_repo.conf_dir) / client_auth_repo.LAST_VALIDATED_FILENAME
    )
    if last_validated_commit_file.exists():
        last_validated_commit_file.unlink()  # Remove the file

    update_and_check_commit_shas(OperationType.UPDATE, origin_auth_repo, client_dir)


@pytest.mark.parametrize(
    "origin_auth_repo",
    [
        {
            "targets_config": [{"name": "target1"}, {"name": "target2"}],
        },
    ],
    indirect=True,
)
def test_update_valid_remove_commits_from_target_repo(origin_auth_repo, client_dir):
    clone_repositories(
        origin_auth_repo,
        client_dir,
    )

    client_target_repo_path = (
        client_dir
        / origin_auth_repo.name
        / "targets/test_remove_commits_from_target_repo0/target1"
    )

    setup_manager = SetupManager(origin_auth_repo)
    setup_manager.add_task(
        remove_commits, kwargs={"repo_path": client_target_repo_path, "num_commits": 1}
    )
    setup_manager.execute_tasks()

    update_and_check_commit_shas(
        OperationType.UPDATE,
        origin_auth_repo,
        client_dir,
        force=True,
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
def test_update_when_target_empty(origin_auth_repo, client_dir):

    clone_repositories(origin_auth_repo, client_dir)

    setup_manager = SetupManager(origin_auth_repo)
    setup_manager.add_task(add_valid_target_commits, kwargs={"add_if_empty": False})
    setup_manager.execute_tasks()

    update_and_check_commit_shas(
        OperationType.UPDATE,
        origin_auth_repo,
        client_dir,
        skip_check_last_validated=True,
    )
    verify_repos_exist(client_dir, origin_auth_repo, excluded=["empty"])


@pytest.mark.parametrize(
    "origin_auth_repo",
    [
        {
            "targets_config": [{"name": "target1"}, {"name": "target2"}],
        },
    ],
    indirect=True,
)
def test_update_valid_when_revert_target(origin_auth_repo, client_dir):
    clone_repositories(origin_auth_repo, client_dir)

    setup_manager = SetupManager(origin_auth_repo)
    setup_manager.add_task(add_valid_target_commits)
    setup_manager.add_task(add_valid_target_commits)
    setup_manager.add_task(add_valid_target_commits)
    setup_manager.execute_tasks()

    update_and_check_commit_shas(
        OperationType.UPDATE,
        origin_auth_repo,
        client_dir,
        skip_check_last_validated=True,
    )
    client_auth_repo = AuthenticationRepository(client_dir, origin_auth_repo.name)
    client_target_repos = load_target_repositories(client_auth_repo)
    setup_manager = SetupManager(client_auth_repo)
    for target_repo in client_target_repos.values():
        setup_manager.add_task(
            remove_commits, kwargs={"repo_path": target_repo.path, "num_commits": 1}
        )
        break
    setup_manager.execute_tasks()
    update_and_check_commit_shas(
        OperationType.UPDATE,
        origin_auth_repo,
        client_dir,
        skip_check_last_validated=True,
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
def test_update_valid_when_several_updates(origin_auth_repo, client_dir):
    clone_repositories(origin_auth_repo, client_dir)

    setup_manager = SetupManager(origin_auth_repo)
    setup_manager.add_task(add_valid_target_commits)
    setup_manager.add_task(add_valid_target_commits)
    setup_manager.execute_tasks()

    update_and_check_commit_shas(
        OperationType.UPDATE,
        origin_auth_repo,
        client_dir,
        skip_check_last_validated=True,
    )
    setup_manager.add_task(add_valid_target_commits)
    setup_manager.add_task(add_valid_target_commits)
    setup_manager.execute_tasks()
    update_and_check_commit_shas(
        OperationType.UPDATE,
        origin_auth_repo,
        client_dir,
        skip_check_last_validated=True,
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
    ],
    indirect=True,
)
def test_update_valid_when_several_updates_when_unauthenticated(
    origin_auth_repo, client_dir
):
    clone_repositories(origin_auth_repo, client_dir)

    setup_manager = SetupManager(origin_auth_repo)
    setup_manager.add_task(add_valid_target_commits)
    setup_manager.add_task(add_valid_unauthenticated_commits)
    setup_manager.execute_tasks()

    update_and_check_commit_shas(
        OperationType.UPDATE,
        origin_auth_repo,
        client_dir,
        skip_check_last_validated=True,
    )
    setup_manager.add_task(add_valid_target_commits)
    setup_manager.execute_tasks()
    update_and_check_commit_shas(
        OperationType.UPDATE,
        origin_auth_repo,
        client_dir,
        skip_check_last_validated=True,
    )


@pytest.mark.parametrize(
    "origin_auth_repo",
    [
        {
            "targets_config": [
                {"name": "target_same1"},
                {"name": "target_same2"},
                {"name": "target_different"},
            ],
        },
    ],
    indirect=True,
)
def test_update_after_update_with_exclude_with_invalid_commits(
    origin_auth_repo, client_dir
):

    clone_repositories(
        origin_auth_repo,
        client_dir,
    )

    is_test_repo = origin_auth_repo.is_test_repo
    expected_repo_type = UpdateType.TEST if is_test_repo else UpdateType.OFFICIAL

    setup_manager = SetupManager(origin_auth_repo)
    setup_manager.add_task(add_valid_target_commits)
    setup_manager.add_task(add_valid_target_commits)
    setup_manager.execute_tasks()

    update_and_check_commit_shas(
        OperationType.UPDATE,
        origin_auth_repo,
        client_dir,
        expected_repo_type=expected_repo_type,
    )

    client_auth_repo = AuthenticationRepository(client_dir, origin_auth_repo.name)
    client_setup_manager = SetupManager(client_auth_repo)
    client_setup_manager.add_task(remove_last_validated_data)
    client_setup_manager.execute_tasks()

    # without the exclusion of the invalid repo, the update should fail
    update_and_check_commit_shas(
        OperationType.UPDATE,
        origin_auth_repo,
        client_dir,
        expected_repo_type=expected_repo_type,
    )
