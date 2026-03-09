from taf.api.repository import reset_repository
import pytest
from taf.auth_repo import AuthenticationRepository
from taf.git import GitRepository
from taf.tests.test_updater.conftest import (
    SetupManager,
    add_valid_target_commits,
    add_file_to_repository,
    update_auth_repo_without_committing,
    update_target_repo_without_committing,
    remove_last_validated_commit,
    INVALID_AUTH_COMMIT_RESET_ERROR,
    UNCOMMITTED_CHANGES_RESET_PATTERN,
    DETACHED_HEAD_RESET_PATTERN,
)
from taf.tests.test_updater.update_utils import (
    clone_repositories,
    update_and_check_commit_shas,
    load_target_repositories,
)
from taf.updater.types.update import OperationType
from taf.models.types import Commitish
from pathlib import Path
from taf.exceptions import ResetFailedError
from typing import Dict, Optional


def prepare_repo_for_reset(
    origin_auth_repo: AuthenticationRepository, client_dir: Path, bare=False
) -> AuthenticationRepository:
    clone_repositories(
        origin_auth_repo,
        client_dir,
    )
    client_auth_repo_path = client_dir / origin_auth_repo.name
    client_auth_repo = AuthenticationRepository(path=client_auth_repo_path)

    setup_manager = SetupManager(origin_auth_repo)
    setup_manager.add_task(add_valid_target_commits)
    setup_manager.execute_tasks()

    update_output = update_and_check_commit_shas(
        OperationType.UPDATE,
        origin_auth_repo,
        client_dir,
        force=True,
        bare=bare,
    )

    assert not len(update_output["auth_repos"][client_auth_repo.name]["warnings"])

    return client_auth_repo


def assert_reset_successful(
    result,
    client_auth_repo: AuthenticationRepository,
    commit_to_reset_to: Commitish,
    target_repos: Dict[str, GitRepository],
    target_commits: Dict,
    lvc: Optional[bool] = False,
):
    assert result is True
    assert client_auth_repo.head_commit() == commit_to_reset_to
    for target_name, target_repo in target_repos.items():
        assert target_repo.head_commit() == target_commits[target_name]
    if lvc:
        assert client_auth_repo.last_validated_commit == commit_to_reset_to.hash


@pytest.mark.parametrize(
    "origin_auth_repo",
    [
        {
            "targets_config": [{"name": "target1"}, {"name": "target2"}],
        },
    ],
    indirect=True,
)
@pytest.mark.parametrize("lvc", [True, False])
@pytest.mark.parametrize("bare", [True, False])
def test_reset_repo_happy_path(origin_auth_repo, client_dir, lvc, bare):
    client_auth_repo = prepare_repo_for_reset(origin_auth_repo, client_dir, bare)
    commit_to_reset_to = client_auth_repo.all_commits_on_branch()[-2]
    all_target_repositories = load_target_repositories(client_auth_repo, client_dir)
    if lvc:
        assert client_auth_repo.last_validated_commit != commit_to_reset_to.hash

    target_commits = {}
    for target_name in all_target_repositories:
        target_commits[target_name] = Commitish.from_hash(
            client_auth_repo.get_target(target_name, commit_to_reset_to)["commit"]
        )

    result = reset_repository(client_auth_repo, commit_to_reset_to.hash, lvc, False)
    assert_reset_successful(
        result,
        client_auth_repo,
        commit_to_reset_to,
        all_target_repositories,
        target_commits,
        lvc,
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
def test_reset_repo_commit_flag_missing_lvc_is_none_expect_fail(
    origin_auth_repo, client_dir
):
    client_auth_repo = prepare_repo_for_reset(origin_auth_repo, client_dir)
    client_setup_manager = SetupManager(client_auth_repo)
    client_setup_manager.add_task(remove_last_validated_commit)
    client_setup_manager.execute_tasks()
    commit_before_reset = client_auth_repo.head_commit()
    with pytest.raises(ResetFailedError, match=INVALID_AUTH_COMMIT_RESET_ERROR):
        reset_repository(client_auth_repo, None, False, False)
    assert commit_before_reset == client_auth_repo.head_commit()


@pytest.mark.parametrize(
    "origin_auth_repo",
    [
        {
            "targets_config": [{"name": "target1"}, {"name": "target2"}],
        },
    ],
    indirect=True,
)
def test_force_reset_repo_auth_repo_has_untracked_file_expect_success(
    origin_auth_repo, client_dir
):
    client_auth_repo = prepare_repo_for_reset(origin_auth_repo, client_dir)
    commit_to_reset_to = client_auth_repo.all_commits_on_branch()[-2]
    add_file_to_repository(client_auth_repo, "test")
    assert client_auth_repo.something_to_commit()

    all_target_repositories = load_target_repositories(client_auth_repo, client_dir)
    target_commits = {}
    for target_name in all_target_repositories:
        target_commits[target_name] = Commitish.from_hash(
            client_auth_repo.get_target(target_name, commit_to_reset_to)["commit"]
        )

    result = reset_repository(client_auth_repo, commit_to_reset_to, False, True)
    assert_reset_successful(
        result,
        client_auth_repo,
        commit_to_reset_to,
        all_target_repositories,
        target_commits,
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
@pytest.mark.parametrize("commit", [None, "not_None"])
def test_reset_repo_auth_repo_has_untracked_file_expect_fail(
    origin_auth_repo, client_dir, commit
):
    client_auth_repo = prepare_repo_for_reset(origin_auth_repo, client_dir)
    commit_to_reset_to = (
        client_auth_repo.all_commits_on_branch()[-2] if commit is not None else None
    )
    add_file_to_repository(client_auth_repo, "test")

    commit_before_reset = client_auth_repo.head_commit()
    all_target_repositories = load_target_repositories(client_auth_repo, client_dir)
    target_commits = {}
    for target_name in all_target_repositories:
        target_commits[target_name] = Commitish.from_hash(
            client_auth_repo.get_target(target_name, commit_to_reset_to)["commit"]
        )

    with pytest.raises(ResetFailedError, match=UNCOMMITTED_CHANGES_RESET_PATTERN):
        reset_repository(client_auth_repo, commit_to_reset_to, False, False)
    assert commit_before_reset == client_auth_repo.head_commit()


@pytest.mark.parametrize(
    "origin_auth_repo",
    [
        {
            "targets_config": [{"name": "target1"}, {"name": "target2"}],
        },
    ],
    indirect=True,
)
def test_force_reset_repo_auth_repo_has_uncommitted_changes_expect_success(
    origin_auth_repo, client_dir
):
    client_auth_repo = prepare_repo_for_reset(origin_auth_repo, client_dir)
    commit_to_reset_to = client_auth_repo.all_commits_on_branch()[-2]
    setup_manager = SetupManager(client_auth_repo)
    setup_manager.add_task(update_auth_repo_without_committing)
    setup_manager.execute_tasks()
    assert client_auth_repo.something_to_commit()

    all_target_repositories = load_target_repositories(client_auth_repo, client_dir)
    target_commits = {}
    for target_name in all_target_repositories:
        target_commits[target_name] = Commitish.from_hash(
            client_auth_repo.get_target(target_name, commit_to_reset_to)["commit"]
        )

    result = reset_repository(client_auth_repo, commit_to_reset_to, False, True)
    assert_reset_successful(
        result,
        client_auth_repo,
        commit_to_reset_to,
        all_target_repositories,
        target_commits,
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
@pytest.mark.parametrize("commit", [None, "not_None"])
def test_reset_repo_auth_repo_has_uncommitted_changes_expect_fail(
    origin_auth_repo, client_dir, commit
):
    client_auth_repo = prepare_repo_for_reset(origin_auth_repo, client_dir)
    commit_to_reset_to = (
        client_auth_repo.all_commits_on_branch()[-2] if commit is not None else None
    )
    setup_manager = SetupManager(client_auth_repo)
    setup_manager.add_task(update_auth_repo_without_committing)
    setup_manager.execute_tasks()
    commit_before_reset = client_auth_repo.head_commit()
    with pytest.raises(ResetFailedError, match=UNCOMMITTED_CHANGES_RESET_PATTERN):
        reset_repository(client_auth_repo, commit_to_reset_to, False, False)
    assert commit_before_reset == client_auth_repo.head_commit()


@pytest.mark.parametrize(
    "origin_auth_repo",
    [
        {
            "targets_config": [{"name": "target1"}, {"name": "target2"}],
        },
    ],
    indirect=True,
)
def test_force_reset_repo_target_repo_has_untracked_file_expect_success(
    origin_auth_repo, client_dir
):
    client_auth_repo = prepare_repo_for_reset(origin_auth_repo, client_dir)
    commit_to_reset_to = client_auth_repo.all_commits_on_branch()[-2]
    all_target_repositories = load_target_repositories(client_auth_repo, client_dir)
    target_repo = next(iter(all_target_repositories.values()))
    add_file_to_repository(target_repo, "test")

    all_target_repositories = load_target_repositories(client_auth_repo, client_dir)
    target_commits = {}
    for target_name, target_repo in all_target_repositories.items():
        if "target1" in target_name:
            assert target_repo.something_to_commit()
        target_commits[target_name] = Commitish.from_hash(
            client_auth_repo.get_target(target_name, commit_to_reset_to)["commit"]
        )

    result = reset_repository(client_auth_repo, commit_to_reset_to, False, True)
    assert_reset_successful(
        result,
        client_auth_repo,
        commit_to_reset_to,
        all_target_repositories,
        target_commits,
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
@pytest.mark.parametrize("commit", [None, "not_None"])
def test_reset_repo_target_repo_has_untracked_file_expect_fail(
    origin_auth_repo, client_dir, commit
):
    client_auth_repo = prepare_repo_for_reset(origin_auth_repo, client_dir)
    commit_to_reset_to = (
        client_auth_repo.all_commits_on_branch()[-2] if commit is not None else None
    )
    all_target_repositories = load_target_repositories(client_auth_repo, client_dir)
    target_repo = next(iter(all_target_repositories.values()))
    add_file_to_repository(target_repo, "test")
    commit_before_reset = client_auth_repo.head_commit()
    with pytest.raises(ResetFailedError, match=UNCOMMITTED_CHANGES_RESET_PATTERN):
        reset_repository(client_auth_repo, commit_to_reset_to, False, False)
    assert commit_before_reset == client_auth_repo.head_commit()


@pytest.mark.parametrize(
    "origin_auth_repo",
    [
        {
            "targets_config": [{"name": "target1"}, {"name": "target2"}],
        },
    ],
    indirect=True,
)
def test_force_reset_repo_target_repo_has_uncommitted_changes_expect_success(
    origin_auth_repo, client_dir
):
    client_auth_repo = prepare_repo_for_reset(origin_auth_repo, client_dir)
    commit_to_reset_to = client_auth_repo.all_commits_on_branch()[-2]
    setup_manager = SetupManager(client_auth_repo)
    setup_manager.add_task(
        update_target_repo_without_committing, kwargs={"target_name": "target1"}
    )
    setup_manager.execute_tasks()

    all_target_repositories = load_target_repositories(client_auth_repo, client_dir)
    target_commits = {}
    for target_name, target_repo in all_target_repositories.items():
        if "target1" in target_name:
            assert target_repo.something_to_commit()
        target_commits[target_name] = Commitish.from_hash(
            client_auth_repo.get_target(target_name, commit_to_reset_to)["commit"]
        )

    result = reset_repository(client_auth_repo, commit_to_reset_to, False, True)
    assert_reset_successful(
        result,
        client_auth_repo,
        commit_to_reset_to,
        all_target_repositories,
        target_commits,
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
@pytest.mark.parametrize("commit", [None, "not_None"])
def test_reset_repo_target_repo_has_uncommitted_changes_expect_fail(
    origin_auth_repo, client_dir, commit
):
    client_auth_repo = prepare_repo_for_reset(origin_auth_repo, client_dir)
    commit_to_reset_to = (
        client_auth_repo.all_commits_on_branch()[-2] if commit is not None else None
    )
    setup_manager = SetupManager(client_auth_repo)
    setup_manager.add_task(
        update_target_repo_without_committing, kwargs={"target_name": "target1"}
    )
    setup_manager.execute_tasks()
    commit_before_reset = client_auth_repo.head_commit()
    with pytest.raises(ResetFailedError, match=UNCOMMITTED_CHANGES_RESET_PATTERN):
        reset_repository(client_auth_repo, commit_to_reset_to, False, False)
    assert commit_before_reset == client_auth_repo.head_commit()


@pytest.mark.parametrize(
    "origin_auth_repo",
    [
        {
            "targets_config": [{"name": "target1"}, {"name": "target2"}],
        },
    ],
    indirect=True,
)
def test_force_reset_repo_auth_repo_detached_head_expect_success(
    origin_auth_repo, client_dir
):
    client_auth_repo = prepare_repo_for_reset(origin_auth_repo, client_dir)
    all_commits = client_auth_repo.all_commits_on_branch()
    commit_to_reset_to = all_commits[-2]
    client_auth_repo.checkout_commit(all_commits[-1])
    assert client_auth_repo.is_detached_head

    all_target_repositories = load_target_repositories(client_auth_repo, client_dir)
    target_commits = {}
    for target_name in all_target_repositories:
        target_commits[target_name] = Commitish.from_hash(
            client_auth_repo.get_target(target_name, commit_to_reset_to)["commit"]
        )

    result = reset_repository(client_auth_repo, commit_to_reset_to, False, True)
    assert_reset_successful(
        result,
        client_auth_repo,
        commit_to_reset_to,
        all_target_repositories,
        target_commits,
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
def test_reset_repo_auth_repo_detached_head_expect_fail(origin_auth_repo, client_dir):
    client_auth_repo = prepare_repo_for_reset(origin_auth_repo, client_dir)
    all_commits = client_auth_repo.all_commits_on_branch()
    commit_to_reset_to = all_commits[-2]
    client_auth_repo.checkout_commit(all_commits[-1])
    with pytest.raises(ResetFailedError, match=DETACHED_HEAD_RESET_PATTERN):
        reset_repository(client_auth_repo, commit_to_reset_to, False, False)


@pytest.mark.parametrize(
    "origin_auth_repo",
    [
        {
            "targets_config": [{"name": "target1"}, {"name": "target2"}],
        },
    ],
    indirect=True,
)
def test_force_reset_repo_target_repo_detached_head_expect_success(
    origin_auth_repo, client_dir
):
    client_auth_repo = prepare_repo_for_reset(origin_auth_repo, client_dir)
    commit_to_reset_to = client_auth_repo.all_commits_on_branch()[-2]

    all_target_repositories = load_target_repositories(client_auth_repo, client_dir)
    target_commits = {}
    for target_name, target_repo in all_target_repositories.items():
        target_commits[target_name] = Commitish.from_hash(
            client_auth_repo.get_target(target_name, commit_to_reset_to)["commit"]
        )
        if "target1" in target_name:
            all_target_commits = target_repo.all_commits_on_branch()
            target_repo.checkout_commit(all_target_commits[-1])
            assert target_repo.is_detached_head

    result = reset_repository(client_auth_repo, commit_to_reset_to, False, True)
    assert_reset_successful(
        result,
        client_auth_repo,
        commit_to_reset_to,
        all_target_repositories,
        target_commits,
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
def test_reset_repo_target_repo_detached_head_expect_fail(origin_auth_repo, client_dir):
    client_auth_repo = prepare_repo_for_reset(origin_auth_repo, client_dir)
    commit_to_reset_to = client_auth_repo.all_commits_on_branch()[-2]

    all_target_repositories = load_target_repositories(client_auth_repo, client_dir)
    target_commits = {}
    for target_name, target_repo in all_target_repositories.items():
        target_commits[target_name] = Commitish.from_hash(
            client_auth_repo.get_target(target_name, commit_to_reset_to)["commit"]
        )
        if "target1" in target_name:
            all_target_commits = target_repo.all_commits_on_branch()
            target_repo.checkout_commit(all_target_commits[-1])
            assert target_repo.is_detached_head
    with pytest.raises(ResetFailedError, match=DETACHED_HEAD_RESET_PATTERN):
        reset_repository(client_auth_repo, commit_to_reset_to, False, False)
