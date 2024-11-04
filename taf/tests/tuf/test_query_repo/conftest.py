
import shutil
from taf.tests.conftest import CLIENT_DIR_PATH
from taf.tuf.repository import TargetFile
from taf.utils import on_rm_error
import pytest
from taf.models.types import RolesKeysData
from taf.tests.test_repository.test_repo import MetadataRepository
from taf.models.converter import from_dict


@pytest.fixture(scope="module", autouse=True)
def repo_dir():
    path = CLIENT_DIR_PATH / "tuf"
    path.mkdir()
    yield path
    shutil.rmtree(path, onerror=on_rm_error)

@pytest.fixture(scope="module")
def tuf_repo(repo_dir, signers, no_yubikeys_input):
    # Create new metadata repository
    path = repo_dir / "repository_without_delegations"
    path.mkdir()
    tuf_repo = MetadataRepository(path)
    roles_keys_data = from_dict(no_yubikeys_input, RolesKeysData)
    tuf_repo.create(roles_keys_data, signers)

    target_file = TargetFile.from_data("foo.txt", b"foo", ["sha256", "sha512"])

    # assert add target file and correct version bumps
    tuf_repo.add_target_files_to_role([target_file])
    yield tuf_repo


@pytest.fixture(scope="module")
def tuf_repo_with_delegations(repo_dir, signers_with_delegations, with_delegations_no_yubikeys_input):
    # Create new metadata repository
    path = repo_dir / "repository_with_delegations"
    path.mkdir()
    tuf_repo = MetadataRepository(path)
    roles_keys_data = from_dict(with_delegations_no_yubikeys_input, RolesKeysData)
    tuf_repo.create(roles_keys_data, signers_with_delegations)

    # assert add target file and correct version bumps
    tuf_repo.add_target_files_to_role([target_file])
    yield tuf_repo
