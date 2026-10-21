import json

from taf.models.types import Commitish
import pytest
from taf.auth_repo import AuthenticationRepository
from taf.tests.test_updater.conftest import (
    DEFAULT_BRANCH_NOT_FOUND_PATTERN,
    INVALID_KEYS_PATTERN,
    INVALID_METADATA_PATTERN,
    LVC_NOT_IN_REMOTE_PATTERN,
    TARGET_MISSING_BRANCH_PATTERN,
    TARGET_MISSMATCH_PATTERN,
    TARGET_MISSMATCH_UNAUTHENTICATED_PATTERN,
    UNCOMMITTED_CHANGES,
    UPDATE_ERROR_PATTERN,
    OLD_LVC_FORMAT_ERROR_PATTERN,
    SetupManager,
    add_unauthenticated_commit_to_target_repo,
    add_unauthenticated_commits_to_all_target_repos,
    add_valid_target_commits,
    create_file_without_committing,
    delete_target_branch,
    point_target_to_unsigned_commit,
    set_last_validated_commit_of_auth_repo,
    switch_target_branch_and_sign,
    update_expiration_dates,
    update_metadata_invalid_signature,
    update_role_metadata_without_signing,
    update_timestamp_metadata_invalid_signature,
    replace_with_old_last_validated_commit_format,
)
from taf.tests.test_updater.update_utils import (
    check_if_last_validated_commit_exists,
    clone_repositories,
    update_invalid_repos_and_check_if_repos_exist,
)
from taf.updater.types.update import OperationType
from taf.updater.updater import UpdateConfig, update_repository
from taf.updater.lifecycle_handlers import Event
from taf.exceptions import UpdateFailedError

from taf.git import GitRepository


@pytest.mark.parametrize(
    "origin_auth_repo",
    [
        {
            "targets_config": [{"name": "target1"}, {"name": "target2"}],
        }
    ],
    indirect=True,
)
def test_update_invalid_delegation_loop_added_without_signing(
    origin_auth_repo, client_dir
):
    clone_repositories(origin_auth_repo, client_dir)

    metadata_dir = origin_auth_repo.path / "metadata"
    targets = json.loads((metadata_dir / "targets.json").read_text())
    targets["signed"]["delegations"] = {
        "keys": {},
        "roles": [
            {
                "name": "loop",
                "keyids": [],
                "threshold": 1,
                "paths": ["loop/*"],
                "terminating": False,
            }
        ],
    }
    # the new role delegates to itself
    (metadata_dir / "targets.json").write_text(json.dumps(targets))
    (metadata_dir / "loop.json").write_text(json.dumps(targets))
    origin_auth_repo.commit("Add a delegation loop without signing")

    update_invalid_repos_and_check_if_repos_exist(
        OperationType.UPDATE,
        origin_auth_repo,
        client_dir,
        UPDATE_ERROR_PATTERN,
        True,
    )
    client_auth_repo = AuthenticationRepository(client_dir, origin_auth_repo.name)
    assert (
        client_auth_repo.last_validated_commit != origin_auth_repo.head_commit().value
    )


@pytest.mark.parametrize(
    "origin_auth_repo",
    [
        {
            "targets_config": [{"name": "target1"}, {"name": "target2"}],
        }
    ],
    indirect=True,
)
def test_update_invalid_metadata_added_without_updating_snapshot(
    origin_auth_repo, client_dir
):
    clone_repositories(origin_auth_repo, client_dir)

    metadata_dir = origin_auth_repo.path / "metadata"
    (metadata_dir / "new_role.json").write_text(
        (metadata_dir / "targets.json").read_text()
    )
    origin_auth_repo.commit("Add metadata without updating snapshot")

    update_invalid_repos_and_check_if_repos_exist(
        OperationType.UPDATE,
        origin_auth_repo,
        client_dir,
        UPDATE_ERROR_PATTERN,
        True,
    )
    client_auth_repo = AuthenticationRepository(client_dir, origin_auth_repo.name)
    assert (
        client_auth_repo.last_validated_commit != origin_auth_repo.head_commit().value
    )


@pytest.mark.parametrize(
    "origin_auth_repo",
    [
        {
            "targets_config": [{"name": "target1"}, {"name": "target2"}],
        }
    ],
    indirect=True,
)
def test_update_invalid_metadata_changed_without_updating_snapshot(
    origin_auth_repo, client_dir
):
    clone_repositories(origin_auth_repo, client_dir)

    setup_manager = SetupManager(origin_auth_repo)
    setup_manager.add_task(
        update_role_metadata_without_signing, kwargs={"role": "targets"}
    )
    setup_manager.execute_tasks()
    origin_auth_repo.commit("Update targets metadata without updating snapshot")

    update_invalid_repos_and_check_if_repos_exist(
        OperationType.UPDATE,
        origin_auth_repo,
        client_dir,
        UPDATE_ERROR_PATTERN,
        True,
    )
    client_auth_repo = AuthenticationRepository(client_dir, origin_auth_repo.name)
    assert (
        client_auth_repo.last_validated_commit != origin_auth_repo.head_commit().value
    )


@pytest.mark.parametrize(
    "origin_auth_repo",
    [
        {
            "targets_config": [{"name": "target1"}, {"name": "target2"}],
        }
    ],
    indirect=True,
)
def test_update_invalid_snapshot_changed_without_updating_timestamp(
    origin_auth_repo, client_dir
):
    clone_repositories(origin_auth_repo, client_dir)

    setup_manager = SetupManager(origin_auth_repo)
    setup_manager.add_task(
        update_metadata_invalid_signature, kwargs={"role": "snapshot"}
    )
    setup_manager.execute_tasks()

    update_invalid_repos_and_check_if_repos_exist(
        OperationType.UPDATE,
        origin_auth_repo,
        client_dir,
        INVALID_METADATA_PATTERN,
        True,
    )
    client_auth_repo = AuthenticationRepository(client_dir, origin_auth_repo.name)
    assert (
        client_auth_repo.last_validated_commit != origin_auth_repo.head_commit().value
    )


@pytest.mark.parametrize(
    "origin_auth_repo",
    [
        {
            "date": "2020-01-01",
            "targets_config": [{"name": "target1"}, {"name": "target2"}],
        }
    ],
    indirect=True,
)
def test_update_invalid_target_changed_in_unsigned_commit_when_metadata_expired(
    origin_auth_repo, client_dir
):
    clone_repositories(origin_auth_repo, client_dir)

    setup_manager = SetupManager(origin_auth_repo)
    setup_manager.add_task(update_expiration_dates, kwargs={"date": "2021-01-01"})
    setup_manager.add_task(
        add_unauthenticated_commit_to_target_repo, kwargs={"target_name": "target1"}
    )
    setup_manager.add_task(
        point_target_to_unsigned_commit, kwargs={"target_name": "target1"}
    )
    setup_manager.execute_tasks()

    update_invalid_repos_and_check_if_repos_exist(
        OperationType.UPDATE,
        origin_auth_repo,
        client_dir,
        UPDATE_ERROR_PATTERN,
        True,
    )
    client_auth_repo = AuthenticationRepository(client_dir, origin_auth_repo.name)
    assert (
        client_auth_repo.last_validated_commit != origin_auth_repo.head_commit().value
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
def test_update_invalid_target_repositories_contain_unsigned_commits(
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


@pytest.mark.parametrize(
    "origin_auth_repo",
    [
        {
            "targets_config": [{"name": "target1"}, {"name": "target2"}],
        },
    ],
    indirect=True,
)
def test_update_invalid_unauthenticated_commit_error_names_the_cause(
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
        TARGET_MISSMATCH_UNAUTHENTICATED_PATTERN,
        True,
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
def test_update_with_uncommitted_target_changes_and_upstream_updates_fails(
    origin_auth_repo, client_dir
):
    clone_repositories(
        origin_auth_repo,
        client_dir,
    )

    create_file_without_committing(origin_auth_repo, client_dir)

    setup_manager = SetupManager(origin_auth_repo)
    setup_manager.add_task(add_valid_target_commits)
    setup_manager.execute_tasks()

    update_invalid_repos_and_check_if_repos_exist(
        OperationType.UPDATE,
        origin_auth_repo,
        client_dir,
        UNCOMMITTED_CHANGES,
        True,
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
def test_update_failure_populates_update_data_on_raised_error(
    origin_auth_repo, client_dir
):
    clone_repositories(
        origin_auth_repo,
        client_dir,
    )

    create_file_without_committing(origin_auth_repo, client_dir)

    setup_manager = SetupManager(origin_auth_repo)
    setup_manager.add_task(add_valid_target_commits)
    setup_manager.execute_tasks()

    config = UpdateConfig(
        operation=OperationType.UPDATE,
        remote_url=str(origin_auth_repo.path),
        update_from_filesystem=True,
        path=str(client_dir / origin_auth_repo.name),
        library_dir=str(client_dir),
    )

    with pytest.raises(UpdateFailedError) as exc_info:
        update_repository(config)

    update_data = exc_info.value.update_data
    assert update_data is not None
    assert update_data["event"] == f"event/{Event.FAILED.value}"
    assert update_data["error_msg"]


@pytest.mark.parametrize(
    "origin_auth_repo",
    [
        {
            "targets_config": [{"name": "target1"}, {"name": "target2"}],
        },
    ],
    indirect=True,
)
def test_update_with_invalid_last_validated_commit(origin_auth_repo, client_dir):
    clone_repositories(origin_auth_repo, client_dir)

    invalid_commit_sha = Commitish.from_hash("66d7f48e972f9fa25196523f469227dfcd85c994")
    client_auth_repo = AuthenticationRepository(client_dir, origin_auth_repo.name)
    clients_setup_manager = SetupManager(client_auth_repo)
    clients_setup_manager.add_task(
        set_last_validated_commit_of_auth_repo, kwargs={"commit": invalid_commit_sha}
    )
    clients_setup_manager.execute_tasks()

    update_invalid_repos_and_check_if_repos_exist(
        OperationType.UPDATE,
        origin_auth_repo,
        client_dir,
        LVC_NOT_IN_REMOTE_PATTERN,
        True,
    )


@pytest.mark.parametrize(
    "origin_auth_repo",
    [
        {
            "targets_config": [{"name": "target1"}, {"name": "target2"}],
        }
    ],
    indirect=True,
)
def test_update_invalid_target_invalid_singature(origin_auth_repo, client_dir):

    clone_repositories(origin_auth_repo, client_dir)

    setup_manager = SetupManager(origin_auth_repo)
    setup_manager.add_task(update_timestamp_metadata_invalid_signature)
    setup_manager.add_task(update_expiration_dates)
    setup_manager.execute_tasks()

    update_invalid_repos_and_check_if_repos_exist(
        OperationType.UPDATE,
        origin_auth_repo,
        client_dir,
        INVALID_KEYS_PATTERN,
        True,
    )
    client_auth_repo = AuthenticationRepository(client_dir, origin_auth_repo.name)
    # make sure that the last validated commit does not exist
    check_if_last_validated_commit_exists(client_auth_repo, True)


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

    update_invalid_repos_and_check_if_repos_exist(
        OperationType.UPDATE,
        origin_auth_repo,
        client_dir,
        OLD_LVC_FORMAT_ERROR_PATTERN,
        True,
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
def test_update_fails_when_target_repo_missing_referenced_branch(
    origin_auth_repo, client_dir
):
    """The auth repo's target metadata pins target1 at a commit on a branch that
    is not present in the target repository. The updater must fail with a clear
    error naming the target repo and the missing branch, not an IndexError/KeyError."""
    clone_repositories(origin_auth_repo, client_dir)

    missing_branch = "missing-branch"

    setup_manager = SetupManager(origin_auth_repo)
    # record a commit on `missing_branch` of target1 in the auth metadata
    setup_manager.add_task(
        switch_target_branch_and_sign,
        kwargs={"target_name": "target1", "branch_name": missing_branch},
    )
    # then remove that branch from the target repo so the auth repo references
    # a branch the target repo no longer contains
    setup_manager.add_task(
        delete_target_branch,
        kwargs={"target_name": "target1", "branch_name": missing_branch},
    )
    setup_manager.execute_tasks()

    update_invalid_repos_and_check_if_repos_exist(
        OperationType.UPDATE,
        origin_auth_repo,
        client_dir,
        TARGET_MISSING_BRANCH_PATTERN,
        True,
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
def test_update_fails_when_default_branch_not_in_local_repo(
    origin_auth_repo, client_dir, monkeypatch
):
    clone_repositories(origin_auth_repo, client_dir)

    monkeypatch.setattr(
        GitRepository,
        "get_default_branch",
        lambda self, url=None: "non-existent-branch",
    )

    update_invalid_repos_and_check_if_repos_exist(
        OperationType.UPDATE,
        origin_auth_repo,
        client_dir,
        DEFAULT_BRANCH_NOT_FOUND_PATTERN,
        True,
    )
