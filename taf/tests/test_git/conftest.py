from pathlib import Path
import shutil
from pytest import fixture
from taf.git import GitRepository
from taf.exceptions import NothingToCommitError
from taf.utils import on_rm_error
from taf.tests.conftest import TEST_DATA_REPOS_PATH


TEST_DIR = Path(TEST_DATA_REPOS_PATH, "test-git")
REPO_NAME = "repository"
CLONE_REPO_NAME = "repository2"


@fixture(scope="session", autouse=True)
def repository():
    path = TEST_DIR / REPO_NAME
    path.mkdir(exist_ok=True, parents=True)
    repo = GitRepository(path=path)
    repo.init_repo()
    (path / "test.txt").write_text("Some example text")
    try:
        repo.commit(message="Add test.txt")
    except NothingToCommitError:
        pass  # this can happen if cleanup was not successful
    yield repo
    repo.cleanup()
    shutil.rmtree(path, onerror=on_rm_error)


@fixture(scope="session", autouse=True)
def clone_repository():
    path = TEST_DIR / CLONE_REPO_NAME
    path.mkdir(exist_ok=True, parents=True)
    repo = GitRepository(path=path)
    yield repo
    repo.cleanup()
    shutil.rmtree(path, onerror=on_rm_error)
