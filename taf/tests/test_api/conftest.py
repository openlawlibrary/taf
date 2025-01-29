import shutil
import uuid
from pathlib import Path
from typing import Dict

import pytest
from _pytest.logging import LogCaptureFixture
from loguru import logger

from taf.api.repository import create_repository
from taf.auth_repo import AuthenticationRepository
from taf.git import GitRepository
from taf.tests.conftest import CLIENT_DIR_PATH, KEYSTORES_PATH, TEST_DATA_PATH
from taf.tests.utils import copy_mirrors_json, copy_repositories_json, read_json
from taf.utils import on_rm_error
from taf.yubikey.yubikey_manager import PinManager

REPOSITORY_DESCRIPTION_INPUT_DIR = TEST_DATA_PATH / "repository_description_inputs"
TEST_INIT_DATA_PATH = Path(__file__).parent.parent / "init_data"
NO_DELEGATIONS_INPUT = REPOSITORY_DESCRIPTION_INPUT_DIR / "no_delegations.json"
NO_YUBIKEYS_INPUT = REPOSITORY_DESCRIPTION_INPUT_DIR / "no_yubikeys.json"
WITH_DELEGATIONS_INPUT = REPOSITORY_DESCRIPTION_INPUT_DIR / "with_delegations.json"
ADD_ROLES_CONFIG_INPUT = REPOSITORY_DESCRIPTION_INPUT_DIR / "add_roles_config.json"
INVALID_PUBLIC_KEY_INPUT = REPOSITORY_DESCRIPTION_INPUT_DIR / "invalid_public_key.json"
WITH_DELEGATIONS_NO_YUBIKEYS_INPUT = (
    REPOSITORY_DESCRIPTION_INPUT_DIR / "with_delegations_no_yubikeys.json"
)
INVALID_KEYS_NUMBER_INPUT = (
    REPOSITORY_DESCRIPTION_INPUT_DIR / "invalid_keys_number.json"
)
INVALID_PATH_INPUT = REPOSITORY_DESCRIPTION_INPUT_DIR / "invalid_path.json"
OLD_YUBIKEY_INPUT = REPOSITORY_DESCRIPTION_INPUT_DIR / "with_old_yubikey.json"

AUTH_REPO_NAME = "auth"
DEPENDENCY_NAME = "dependency/auth"


@pytest.fixture(scope="module")
def api_repo_path(repo_dir):
    path = repo_dir / "api" / "auth"
    yield path
    shutil.rmtree(path.parent, onerror=on_rm_error)


@pytest.fixture(scope="session")
def no_delegations_json_input():
    return read_json(NO_DELEGATIONS_INPUT)


@pytest.fixture(scope="session")
def with_delegations_json_input():
    return read_json(WITH_DELEGATIONS_INPUT)


@pytest.fixture(scope="session")
def add_roles_config_json_input():
    return read_json(ADD_ROLES_CONFIG_INPUT)


@pytest.fixture(scope="session")
def invalid_public_key_json_input():
    return read_json(INVALID_PUBLIC_KEY_INPUT)


@pytest.fixture(scope="session")
def invalid_keys_number_json_input():
    return read_json(INVALID_KEYS_NUMBER_INPUT)


@pytest.fixture(scope="session")
def invalid_path_input():
    return read_json(INVALID_PATH_INPUT)


@pytest.fixture(scope="session")
def with_old_yubikey_input():
    return read_json(OLD_YUBIKEY_INPUT)


@pytest.fixture
def auth_repo_path(repo_dir):
    random_name = str(uuid.uuid4())
    path = repo_dir / "api" / random_name / "auth"
    yield path
    shutil.rmtree(path.parent, onerror=on_rm_error)


@pytest.fixture
def auth_repo(auth_repo_path, keystore_delegations, no_yubikeys_path, pin_manager):
    repo_path = str(auth_repo_path)
    create_repository(
        repo_path,
        pin_manager,
        roles_key_infos=no_yubikeys_path,
        keystore=keystore_delegations,
        commit=True,
        test=True,
    )
    auth_repo = AuthenticationRepository(path=repo_path)
    yield auth_repo


@pytest.fixture
def auth_repo_with_delegations(
    auth_repo_path, keystore_delegations, with_delegations_no_yubikeys_path, pin_manager
):
    repo_path = str(auth_repo_path)
    create_repository(
        repo_path,
        pin_manager,
        roles_key_infos=with_delegations_no_yubikeys_path,
        keystore=keystore_delegations,
        commit=True,
        test=True,
    )
    auth_repo = AuthenticationRepository(path=repo_path)
    yield auth_repo


@pytest.fixture(scope="session")
def no_yubikeys_json_input():
    return read_json(NO_YUBIKEYS_INPUT)


@pytest.fixture(scope="session")
def no_yubikeys_path():
    return str(NO_YUBIKEYS_INPUT)


@pytest.fixture(scope="module")
def library(repo_dir):
    random_name = str(uuid.uuid4())
    root_dir = repo_dir / random_name
    # create an initialize some target repositories
    # their content is not important
    auth_path = root_dir / AUTH_REPO_NAME
    auth_path.mkdir(exist_ok=True, parents=True)
    targets = ("target1", "target2", "target3", "new_target")
    for target in targets:
        target_repo_path = root_dir / target
        target_repo_path.mkdir()
        target_repo = GitRepository(path=target_repo_path)
        target_repo.init_repo()
        target_repo.commit_empty("Initial commit")
    yield root_dir
    shutil.rmtree(root_dir, onerror=on_rm_error)


@pytest.fixture(scope="function")
def auth_repo_when_add_repositories_json(
    library: Path,
    with_delegations_no_yubikeys_path: str,
    keystore_delegations: str,
    repositories_json_template: Dict,
    mirrors_json_path: Path,
    pin_manager: PinManager,
):
    repo_path = library / "auth"
    namespace = library.name
    copy_repositories_json(repositories_json_template, namespace, repo_path)
    copy_mirrors_json(mirrors_json_path, repo_path)
    create_repository(
        str(repo_path),
        pin_manager=pin_manager,
        roles_key_infos=with_delegations_no_yubikeys_path,
        keystore=keystore_delegations,
        commit=True,
    )
    auth_reo = AuthenticationRepository(path=repo_path)
    yield auth_reo
    shutil.rmtree(repo_path, onerror=on_rm_error)


def _init_auth_repo_dir():
    random_name = str(uuid.uuid4())
    root_dir = CLIENT_DIR_PATH / random_name
    auth_path = root_dir / AUTH_REPO_NAME
    auth_path.mkdir(exist_ok=True, parents=True)
    return auth_path


@pytest.fixture(scope="module")
def child_repo_path():
    repo_path = _init_auth_repo_dir()
    yield repo_path
    shutil.rmtree(str(repo_path.parent), onerror=on_rm_error)


@pytest.fixture(scope="module")
def parent_repo_path():
    repo_path = _init_auth_repo_dir()
    yield repo_path
    shutil.rmtree(str(repo_path.parent), onerror=on_rm_error)


@pytest.fixture(scope="module")
def roles_keystore(keystore_delegations):
    # set up a keystore by copying the api keystore
    # new keystore files are expected to be created and store to this directory
    # it will be removed once this test's execution is done
    # Create the destination folder if it doesn't exist
    roles_keystore = KEYSTORES_PATH / "roles_keystore"
    if roles_keystore.is_dir():
        shutil.rmtree(str(roles_keystore))

    # Copy the contents of the source folder to the destination folder
    shutil.copytree(keystore_delegations, str(roles_keystore))
    yield str(roles_keystore)
    shutil.rmtree(str(roles_keystore))


@pytest.fixture
def caplog(caplog: LogCaptureFixture):
    """
    Override pytest capture logging (caplog fixture) to point to loguru logging instead.
    This is because we use loguru logging instead of the default logging module.
    Source: https://loguru.readthedocs.io/en/stable/resources/migration.html#replacing-caplog-fixture-from-pytest-library
    """
    handler_id = logger.add(
        caplog.handler,
        format="{message}",
        level=0,
        filter=lambda record: record["level"].no >= caplog.handler.level,
        enqueue=False,  # Set to 'True' if your test is spawning child processes.
    )
    yield caplog
    logger.remove(handler_id)
