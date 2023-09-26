import json
import os
import uuid
import shutil

from pathlib import Path
from taf.tests.conftest import KEYSTORES_PATH, TEST_DATA_PATH, CLIENT_DIR_PATH
from taf.auth_repo import AuthenticationRepository
from taf.utils import on_rm_error

from pytest import fixture


REPOSITORY_DESCRIPTION_INPUT_DIR = TEST_DATA_PATH / "repository_description_inputs"
NO_DELEGATIONS_INPUT = REPOSITORY_DESCRIPTION_INPUT_DIR / "no_delegations.json"
NO_YUBIKEYS_INPUT = REPOSITORY_DESCRIPTION_INPUT_DIR / "no_yubikeys.json"
WITH_DELEGATIONS_INPUT = REPOSITORY_DESCRIPTION_INPUT_DIR / "with_delegations.json"
INVALID_PUBLIC_KEY_INPUT = REPOSITORY_DESCRIPTION_INPUT_DIR / "invalid_public_key.json"
WITH_DELEGATIONS_NO_YUBIKEYS_INPUT = REPOSITORY_DESCRIPTION_INPUT_DIR / "with_delegations_no_yubikeys.json"
INVALID_KEYS_NUMBER_INPUT = (
    REPOSITORY_DESCRIPTION_INPUT_DIR / "invalid_keys_number.json"
)
INVALID_PATH_INPUT = REPOSITORY_DESCRIPTION_INPUT_DIR / "invalid_path.json"
OLD_YUBIKEY_INPUT = REPOSITORY_DESCRIPTION_INPUT_DIR / "with_old_yubikey.json"

KEYSTORE_PATH = KEYSTORES_PATH / "api_keystore"


def _read_json(path):
    return json.loads(Path(path).read_text())


@fixture
def api_keystore():
    return str(KEYSTORE_PATH)


@fixture
def auth_repository_path():
    root_path = CLIENT_DIR_PATH / "namespace"
    yield str(root_path / "auth")
    shutil.rmtree(root_path, onerror=on_rm_error)

@fixture(scope="function")
def auth_repo():
    random_name = str(uuid.uuid4())
    root_name = f"{random_name}/auth"
    auth_repo = AuthenticationRepository(CLIENT_DIR_PATH, root_name)
    yield auth_repo
    shutil.rmtree(str(auth_repo.path), onerror=on_rm_error)
    os.rmdir(str(CLIENT_DIR_PATH / random_name))


@fixture
def no_delegations_json_input():
    return _read_json(NO_DELEGATIONS_INPUT)

@fixture
def no_delegations_json_input():
    return _read_json(NO_DELEGATIONS_INPUT)


@fixture
def no_yubikeys_json_input():
    return _read_json(NO_YUBIKEYS_INPUT)


@fixture
def with_delegations_no_yubikeys_path():
    return str(WITH_DELEGATIONS_NO_YUBIKEYS_INPUT)

@fixture
def no_yubikeys_path():
    return str(WITH_DELEGATIONS_NO_YUBIKEYS_INPUT)


@fixture
def with_delegations_json_input():
    return _read_json(WITH_DELEGATIONS_INPUT)


@fixture
def invalid_public_key_json_input():
    return _read_json(INVALID_PUBLIC_KEY_INPUT)


@fixture
def invalid_keys_number_json_input():
    return _read_json(INVALID_KEYS_NUMBER_INPUT)


@fixture
def invalid_path_input():
    return _read_json(INVALID_PATH_INPUT)


@fixture
def with_old_yubikey():
    return _read_json(OLD_YUBIKEY_INPUT)

