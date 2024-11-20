import shutil
import uuid

from taf.utils import on_rm_error
from pytest import fixture

@fixture(scope="module", autouse=True)
def tuf_repo_dir(repo_dir):
    path = repo_dir / "tuf"
    path.mkdir()
    yield path
    shutil.rmtree(path, onerror=on_rm_error)

@fixture
def tuf_repo_path(tuf_repo_dir):
    random_name = str(uuid.uuid4())
    path = tuf_repo_dir / random_name / "auth"
    yield path
    shutil.rmtree(path.parent, onerror=on_rm_error)
