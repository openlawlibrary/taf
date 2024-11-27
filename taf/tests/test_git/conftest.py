from pathlib import Path
import shutil
import pytest
from taf.git import GitRepository
from taf.exceptions import NothingToCommitError
from taf.utils import on_rm_error
from taf.tests.conftest import TEST_DATA_REPOS_PATH


TEST_DIR = Path(TEST_DATA_REPOS_PATH, "test-git")
REPO_NAME = "repository"
CLONE_REPO_NAME = "repository2"


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
