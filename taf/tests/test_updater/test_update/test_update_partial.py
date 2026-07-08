from pathlib import Path

import pytest
from taf.auth_repo import AuthenticationRepository
from taf.git import GitRepository
from taf.tests.test_updater.conftest import (
    TARGET_MISSMATCH_PATTERN,
    SetupManager,
    add_unauthenticated_commit_to_target_repo,
    add_valid_target_commits,
    set_head_commit,
    update_target_repo_without_committing,
)
from taf.tests.test_updater.update_utils import (
    UpdateType,
    clone_repositories,
    load_target_repositories,
    update_and_check_commit_shas,
    update_invalid_repos_and_check_if_repos_exist,
    verify_excluded_lvc_entries,
    verify_repos_exist,
)
from taf.updater.types.update import OperationType


@pytest.mark.parametrize(
    "origin_auth_repo",
    [
        {
            "targets_config": [{"name": "target1"}, {"name": "target2"}],
        },
    ],
    indirect=True,
)
def test_update_partial_with_invalid_commits(origin_auth_repo, client_dir):
    clone_repositories(
        origin_auth_repo,
        client_dir,
    )
    client_auth_repo_path = client_dir / origin_auth_repo.name
    client_auth_repo = AuthenticationRepository(path=client_auth_repo_path)

    setup_manager = SetupManager(origin_auth_repo)
    setup_manager.add_task(add_valid_target_commits)
    setup_manager.execute_tasks()

    setup_manager.add_task(set_head_commit)

    setup_manager.add_task(add_valid_target_commits)
    setup_manager.execute_tasks()

    setup_manager = SetupManager(client_auth_repo)
    setup_manager.add_task(
        update_target_repo_without_committing, kwargs={"target_name": "target1"}
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
                {"name": "target_same1"},
                {"name": "target_same2"},
                {"name": "target_different"},
            ],
        },
    ],
    indirect=True,
)
def test_update_when_clone_with_excluded_update_all(origin_auth_repo, client_dir):

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
        exclude_filter="'target_same' in repo['name']",
    )
    verify_excluded_lvc_entries(client_dir, origin_auth_repo, excluded=["target_same"])

    update_and_check_commit_shas(
        OperationType.UPDATE,
        origin_auth_repo,
        client_dir,
        expected_repo_type=expected_repo_type,
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
def test_full_update_after_partial_clone(origin_auth_repo, client_dir):
    setup_manager = SetupManager(origin_auth_repo)
    setup_manager.add_task(add_valid_target_commits)
    setup_manager.add_task(add_valid_target_commits)
    setup_manager.execute_tasks()
    is_test_repo = origin_auth_repo.is_test_repo
    expected_repo_type = UpdateType.TEST if is_test_repo else UpdateType.OFFICIAL

    update_and_check_commit_shas(
        OperationType.CLONE,
        origin_auth_repo,
        client_dir,
        expected_repo_type=expected_repo_type,
        exclude_filter="'target_same' in repo['name']",
    )
    excluded = ["target_same1", "target_same2"]
    verify_repos_exist(client_dir, origin_auth_repo, excluded)
    verify_excluded_lvc_entries(client_dir, origin_auth_repo, excluded)
    # this update should be successful because we are skipping the invalid repo
    update_and_check_commit_shas(
        OperationType.UPDATE,
        origin_auth_repo,
        client_dir,
        no_upstream=False,
        expected_repo_type=expected_repo_type,
    )
    verify_repos_exist(client_dir, origin_auth_repo, excluded)
    verify_excluded_lvc_entries(client_dir, origin_auth_repo, excluded)


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
def test_update_after_partial_clone_with_deleted_lvc(origin_auth_repo, client_dir):
    """Clone with exclude_filter, delete last_validated_commit, then update."""
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
        exclude_filter="'target_same' in repo['name']",
    )

    excluded = ["target_same1", "target_same2"]
    verify_repos_exist(client_dir, origin_auth_repo, excluded)
    verify_excluded_lvc_entries(client_dir, origin_auth_repo, excluded)

    # Delete the last_validated_commit file
    client_auth_repo = AuthenticationRepository(path=client_dir / origin_auth_repo.name)
    lvc_path = Path(client_auth_repo.conf_dir, client_auth_repo.LAST_VALIDATED_FILENAME)
    assert lvc_path.is_file()
    lvc_path.unlink()

    # Update should still succeed — re-validates from scratch
    update_and_check_commit_shas(
        OperationType.UPDATE,
        origin_auth_repo,
        client_dir,
        expected_repo_type=expected_repo_type,
        skip_check_last_validated=True,
    )
    verify_repos_exist(client_dir, origin_auth_repo)


@pytest.mark.parametrize(
    "origin_auth_repo",
    [
        {
            "targets_config": [
                {"name": "target_type1", "custom": {"type": "type1"}},
                {"name": "target_type2", "custom": {"type": "type2"}},
            ],
        },
    ],
    indirect=True,
)
def test_update_after_clone_with_type1_filter_remove_exclude_from_lvc(
    origin_auth_repo, client_dir
):
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
        exclude_filter="repo['type'] == 'type1'",
    )
    verify_repos_exist(client_dir, origin_auth_repo, excluded=["target_type1"])
    verify_excluded_lvc_entries(client_dir, origin_auth_repo, excluded=["target_type1"])

    # Remove exclude_filter from LVC so the next update includes all repos
    client_auth_repo = AuthenticationRepository(path=client_dir / origin_auth_repo.name)
    lvc_data = client_auth_repo.last_validated_data
    lvc_data.pop("exclude_filter", None)
    client_auth_repo.set_last_validated_data(lvc_data, set_last_validated_commit=False)

    # Update should now clone and validate all repos, including type1
    update_and_check_commit_shas(
        OperationType.UPDATE,
        origin_auth_repo,
        client_dir,
        expected_repo_type=expected_repo_type,
    )
    verify_repos_exist(client_dir, origin_auth_repo)


@pytest.mark.parametrize(
    "origin_auth_repo",
    [
        {
            "targets_config": [
                {"name": "target_type1", "custom": {"type": "type1"}},
                {"name": "target_type2a"},
                {"name": "target_type2b"},
            ],
        },
    ],
    indirect=True,
)
def test_last_validated_commit_set_on_exclude_not_updated_on_partial_error(
    origin_auth_repo, client_dir
):
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
        exclude_filter="repo['type'] == 'type1'",
    )

    client_auth_repo = AuthenticationRepository(path=client_dir / origin_auth_repo.name)
    lvc_data = client_auth_repo.last_validated_data
    assert client_auth_repo.LAST_VALIDATED_KEY in lvc_data
    assert (
        lvc_data[client_auth_repo.LAST_VALIDATED_KEY]
        == client_auth_repo.head_commit().hash
    )

    # Sandwich target_type2b: valid -> unsigned -> valid again, so there is an unsigned commit
    setup_manager.add_task(add_valid_target_commits)
    setup_manager.add_task(
        add_unauthenticated_commit_to_target_repo,
        kwargs={"target_name": "target_type2b"},
    )
    setup_manager.add_task(add_valid_target_commits)
    setup_manager.execute_tasks()

    client_target_repos = load_target_repositories(
        origin_auth_repo, library_dir=client_dir
    )
    client_type2a = next(
        repo for name, repo in client_target_repos.items() if "target_type2a" in name
    )

    # Update partially fails: type2b has an unsigned commit sandwiched between two signed commits
    update_invalid_repos_and_check_if_repos_exist(
        OperationType.UPDATE,
        origin_auth_repo,
        client_dir,
        TARGET_MISSMATCH_PATTERN,
        expect_partial_update=True,
    )

    # target_type2a (only valid commits) was fully updated to match the origin
    origin_type2a = GitRepository(
        origin_auth_repo.path.parent.parent, client_type2a.name
    )
    assert client_type2a.head_commit() == origin_type2a.head_commit()

    # last_validated_commit was not updated to the latest origin auth head —
    # it reflects only the last auth commit where all repos were fully consistent
    assert (
        client_auth_repo.last_validated_data[client_auth_repo.LAST_VALIDATED_KEY]
        != origin_auth_repo.head_commit().hash
    )
