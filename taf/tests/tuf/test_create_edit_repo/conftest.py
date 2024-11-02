import shutil

from taf.utils import on_rm_error
import pytest
from taf.tests.conftest import CLIENT_DIR_PATH


@pytest.fixture(autouse=True)
def repo_dir():
    path = CLIENT_DIR_PATH / "tuf-edit"
    if path.is_dir():
        shutil.rmtree(path, onerror=on_rm_error)
    path.mkdir(parents=True)
    yield path
    shutil.rmtree(path, onerror=on_rm_error)


@pytest.fixture(autouse=True)
def repo_path(request, repo_dir):
    # Get the base directory path

    # Append the test name
    test_name = request.node.name
    full_path = repo_dir / test_name
    full_path.mkdir()

    # Convert to string if necessary, or use it as a Path object
    return full_path
