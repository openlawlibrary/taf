from pathlib import Path
import shutil
from typing import Optional
import pytest
from taf.git import GitRepository
from taf.models.types import Commitish
from taf.exceptions import NothingToCommitError
from taf.utils import on_rm_error
from taf.tests.conftest import TEST_DATA_REPOS_PATH

TEST_DIR = Path(TEST_DATA_REPOS_PATH, "test-git")
REPO_NAME = "repository"
CLONE_REPO_NAME = "repository2"
ORIGIN_REPO_NAME = "origin_repo"


@pytest.fixture
def repository():
    path = TEST_DIR / REPO_NAME
    path.mkdir(exist_ok=True, parents=True)
    repo = GitRepository(path=path)
    repo.init_repo()
    try:
        (path / "test1.txt").write_text("Some example text 1")
        repo.commit(message="Add test1.txt")
        (path / "test2.txt").write_text("Some example text 2")
        repo.commit(message="Add test2.txt")
        (path / "test3.txt").write_text("Some example text 3")
        repo.commit(message="Add test3.txt")
    except NothingToCommitError:
        pass  # this can happen if cleanup was not successful

    yield repo
    repo.cleanup()
    shutil.rmtree(path, onerror=on_rm_error)


@pytest.fixture
def origin_repo(repository):
    path = TEST_DIR / ORIGIN_REPO_NAME
    repo = GitRepository(path=path)
    repo.clone_from_disk(repository.path, is_bare=True)
    yield repo
    repo.cleanup()
    shutil.rmtree(path, onerror=on_rm_error)


@pytest.fixture
def clone_repository():
    path = TEST_DIR / CLONE_REPO_NAME
    path.mkdir(exist_ok=True, parents=True)
    repo = GitRepository(path=path)
    yield repo
    repo.cleanup()
    shutil.rmtree(path, onerror=on_rm_error)


@pytest.fixture
def empty_repository():
    path = TEST_DIR / CLONE_REPO_NAME
    path.mkdir(exist_ok=True, parents=True)
    repo = GitRepository(path=path)
    repo.init_repo()
    yield repo
    repo.cleanup()
    shutil.rmtree(path, onerror=on_rm_error)


@pytest.fixture
def cloned_repository(origin_repo, clone_repository):
    clone_repository.urls = [str(origin_repo.path)]
    clone_repository.clone()
    return clone_repository


def push_new_branch(
    repo: GitRepository, branch: str, with_commit: bool = False
) -> Optional[Commitish]:
    """Push a new branch to origin and return to the branch that was checked out."""
    default_branch = repo.get_current_branch()
    repo.checkout_branch(branch, create=True)
    commit = repo.commit_empty(f"commit on {branch}") if with_commit else None
    repo.push(branch=branch)
    repo.checkout_branch(default_branch)
    return commit


def push_commit_then_reset(repo: GitRepository) -> Commitish:
    """Push a new commit, then move the local branch back so it is behind origin."""
    pushed_commit = repo.commit_empty("upstream commit")
    repo.push()
    repo.reset_num_of_commits(1, hard=True)
    return pushed_commit
