import pytest
from taf.tests.test_updater.conftest import (
    SetupManager,
    add_valid_target_commits,
    switch_target_branch_and_sign,
)
from taf.tests.test_updater.update_utils import (
    load_target_repositories,
    update_invalid_repos_and_check_if_repos_exist,
)
from taf.updater.types.update import OperationType


@pytest.mark.parametrize(
    "origin_auth_repo",
    [{"targets_config": [{"name": "target1"}, {"name": "target2"}]}],
    indirect=True,
)
def test_clone_fails_when_target_switches_branch(origin_auth_repo, client_dir):
    """When a target repo moves to a new branch mid-history, cloning fails because
    the updater presents the first (root) commit of new-branch as the expected
    starting point, but the auth repo signed the new tip — those two differ."""
    setup_manager = SetupManager(origin_auth_repo)
    setup_manager.add_task(add_valid_target_commits)
    setup_manager.add_task(add_valid_target_commits)
    setup_manager.add_task(
        switch_target_branch_and_sign,
        kwargs={"target_name": "target1", "branch_name": "new-branch"},
    )
    setup_manager.execute_tasks()

    origin_target_repos = load_target_repositories(origin_auth_repo)
    target1_repo = next(r for r in origin_target_repos.values() if "target1" in r.name)

    first_commit = target1_repo.get_first_commit_on_branch("new-branch")
    signed_commit = target1_repo.all_commits_on_branch("new-branch")[-1]

    expected_error = (
        rf"was supposed to be at commit {signed_commit.value} "
        rf"but repo was at {first_commit.value}"
    )

    update_invalid_repos_and_check_if_repos_exist(
        OperationType.CLONE,
        origin_auth_repo,
        client_dir,
        expected_error,
        expect_partial_update=True,
    )
