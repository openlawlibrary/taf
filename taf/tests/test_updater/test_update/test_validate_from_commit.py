import pytest
from taf.auth_repo import AuthenticationRepository
from taf.updater.updater import validate_repository
from taf.tests.test_updater.conftest import (
    SetupManager,
    add_valid_target_commits,
    create_new_target_orphan_branches,
)
from taf.tests.test_updater.update_utils import (
    clone_repositories,
    load_target_repositories,
    update_and_check_commit_shas,
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
def test_validate_from_commit_preserved_after_branch_switch(
    origin_auth_repo, client_dir
):
    clone_repositories(origin_auth_repo, client_dir)

    setup_manager = SetupManager(origin_auth_repo)
    setup_manager.add_task(add_valid_target_commits)
    setup_manager.execute_tasks()

    update_and_check_commit_shas(
        OperationType.UPDATE,
        origin_auth_repo,
        client_dir,
    )

    # Validate later from the last commit prior to rewriting target history.
    mid_point_commit = origin_auth_repo.head_commit()

    setup_manager.add_task(
        create_new_target_orphan_branches, kwargs={"branch_name": "branch1"}
    )
    setup_manager.add_task(add_valid_target_commits)
    setup_manager.execute_tasks()

    validate_repository(
        str(origin_auth_repo.path),
        library_dir=str(origin_auth_repo.path.parent.parent),
        validate_from_commit=mid_point_commit.value,
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
def test_validate_succeeds_when_target_local_branch_deleted_but_remote_exists(
    origin_auth_repo, client_dir
):
    setup_manager = SetupManager(origin_auth_repo)
    setup_manager.add_task(add_valid_target_commits)
    setup_manager.execute_tasks()

    clone_repositories(origin_auth_repo, client_dir)

    client_target_repos = load_target_repositories(origin_auth_repo, client_dir)
    first_target_repo = list(client_target_repos.values())[0]

    default_branch = first_target_repo.default_branch

    first_target_repo.create_and_checkout_branch("test-branch")
    first_target_repo.delete_local_branch(default_branch)

    assert not first_target_repo.branch_exists(default_branch, include_remotes=False)
    assert first_target_repo.find_remote_tracking_branch(default_branch) is not None

    client_auth_repo = AuthenticationRepository(client_dir, origin_auth_repo.name)
    first_commit = client_auth_repo.get_first_commit_on_branch(
        client_auth_repo.default_branch
    )

    validate_repository(
        str(client_auth_repo.path),
        library_dir=str(client_dir),
        validate_from_commit=first_commit.value,
    )
