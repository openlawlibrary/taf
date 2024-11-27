import json
import pytest
from pathlib import Path
import shutil
import uuid

from taf.api.repository import create_repository
from taf.auth_repo import AuthenticationRepository
from taf.tests.conftest import TEST_DATA_PATH
from taf.utils import on_rm_error


REPOSITORY_DESCRIPTION_INPUT_DIR = TEST_DATA_PATH / "repository_description_inputs"
TEST_INIT_DATA_PATH = Path(__file__).parent.parent / "init_data"
NO_DELEGATIONS_INPUT = REPOSITORY_DESCRIPTION_INPUT_DIR / "no_delegations.json"
NO_YUBIKEYS_INPUT = REPOSITORY_DESCRIPTION_INPUT_DIR / "no_yubikeys.json"
WITH_DELEGATIONS_INPUT = REPOSITORY_DESCRIPTION_INPUT_DIR / "with_delegations.json"
INVALID_PUBLIC_KEY_INPUT = REPOSITORY_DESCRIPTION_INPUT_DIR / "invalid_public_key.json"
WITH_DELEGATIONS_NO_YUBIKEYS_INPUT = (
    REPOSITORY_DESCRIPTION_INPUT_DIR / "with_delegations_no_yubikeys.json"
)
INVALID_KEYS_NUMBER_INPUT = (
    REPOSITORY_DESCRIPTION_INPUT_DIR / "invalid_keys_number.json"
)
INVALID_PATH_INPUT = REPOSITORY_DESCRIPTION_INPUT_DIR / "invalid_path.json"
OLD_YUBIKEY_INPUT = REPOSITORY_DESCRIPTION_INPUT_DIR / "with_old_yubikey.json"


def _read_json(path):
    return json.loads(Path(path).read_text())


@fixture
def auth_repo_path(repo_dir):
    random_name = str(uuid.uuid4())
    path = repo_dir / "api" / random_name / "auth"
    yield path
    shutil.rmtree(path.parent, onerror=on_rm_error)


@fixture
def auth_repo(auth_repo_path, keystore_delegations, no_yubikeys_path):
    repo_path = str(auth_repo_path)
    create_repository(
        repo_path,
        roles_key_infos=no_yubikeys_path,
        keystore=keystore_delegations,
        commit=True,
        test=True,
    )
    auth_repo = AuthenticationRepository(path=repo_path)
    yield auth_repo


@fixture
def auth_repo_with_delegations(
    auth_repo_path, keystore_delegations, with_delegations_no_yubikeys_path
):
    repo_path = str(auth_repo_path)
    create_repository(
        repo_path,
        roles_key_infos=with_delegations_no_yubikeys_path,
        keystore=keystore_delegations,
        commit=True,
        test=True,
    )
    auth_repo = AuthenticationRepository(path=repo_path)
    yield auth_repo


@fixture(scope="module")
def api_repo_path(repo_dir):
    path = repo_dir / "api" / "auth"
    yield path
    shutil.rmtree(path.parent, onerror=on_rm_error)


@fixture(scope="session")
def no_delegations_json_input():
    return _read_json(NO_DELEGATIONS_INPUT)


@fixture(scope="session")
def no_yubikeys_json_input():
    return _read_json(NO_YUBIKEYS_INPUT)


@fixture(scope="session")
def no_yubikeys_path():
    return str(NO_YUBIKEYS_INPUT)


@fixture(scope="session")
def with_delegations_json_input():
    return _read_json(WITH_DELEGATIONS_INPUT)


@fixture(scope="session")
def invalid_public_key_json_input():
    return _read_json(INVALID_PUBLIC_KEY_INPUT)


@fixture(scope="session")
def invalid_keys_number_json_input():
    return _read_json(INVALID_KEYS_NUMBER_INPUT)


@fixture(scope="session")
def invalid_path_input():
    return _read_json(INVALID_PATH_INPUT)


@fixture(scope="session")
def with_old_yubikey_input():
    return _read_json(OLD_YUBIKEY_INPUT)
