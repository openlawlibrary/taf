import pytest
from taf.updater.updater import validate_repository
from taf.tests.test_updater.conftest import (
    SetupManager,
    add_valid_target_commits,
    create_new_target_orphan_branches,
)
from taf.tests.test_updater.update_utils import (
    clone_repositories,
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
    # 1. Clone and add initial target commits
    clone_repositories(origin_auth_repo, client_dir)

    setup_manager = SetupManager(origin_auth_repo)
    setup_manager.add_task(add_valid_target_commits)
    setup_manager.execute_tasks()

    # 2. Update client so it's in sync
    update_and_check_commit_shas(
        OperationType.UPDATE,
        origin_auth_repo,
        client_dir,
    )

    # Record the commit BEFORE we switch branches
    mid_point_commit = origin_auth_repo.head_commit()

    # 3. Switch targets to a new orphan branch and add more commits
    setup_manager.add_task(
        create_new_target_orphan_branches, kwargs={"branch_name": "branch1"}
    )
    setup_manager.add_task(add_valid_target_commits)
    setup_manager.execute_tasks()

    # 4. Validate from mid_point_commit on the ORIGIN repo (no last_validated_data)
    validate_repository(
        str(origin_auth_repo.path),
        library_dir=str(origin_auth_repo.path.parent.parent),
        validate_from_commit=mid_point_commit.value,
    )
