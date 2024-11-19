import os
import shutil
from contextlib import contextmanager
from pathlib import Path


from pytest import fixture
from taf.tests import TEST_WITH_REAL_YK
from taf.utils import on_rm_error

TEST_DATA_PATH = Path(__file__).parent / "data"
TEST_DATA_REPOS_PATH = TEST_DATA_PATH / "repos"
TEST_DATA_ORIGIN_PATH = TEST_DATA_REPOS_PATH / "origin"
TEST_OUTPUT_PATH = TEST_DATA_PATH / "output"
KEYSTORES_PATH = TEST_DATA_PATH / "keystores"
KEYSTORE_PATH = KEYSTORES_PATH / "keystore"
WRONG_KEYSTORE_PATH = KEYSTORES_PATH / "wrong_keystore"
DELEGATED_ROLES_KEYSTORE_PATH = KEYSTORES_PATH / "delegated_roles_keystore"
CLIENT_DIR_PATH = TEST_DATA_REPOS_PATH / "client"
HANDLERS_DATA_INPUT_DIR = TEST_DATA_PATH / "handler_inputs"
TEST_INIT_DATA_PATH = Path(__file__).parent / "init_data"


def pytest_generate_tests(metafunc):
    if "repositories" in metafunc.fixturenames:
        # When running tests with real yubikey, use just rsa-pkcs1v15-sha256 scheme
        schemes = (
            ["rsa-pkcs1v15-sha256"]
            if TEST_WITH_REAL_YK
            else ["rsassa-pss-sha256", "rsa-pkcs1v15-sha256"]
        )
        metafunc.parametrize("repositories", schemes, indirect=True)


@fixture(scope="module", autouse=True)
def repo_dir():
    path = CLIENT_DIR_PATH / "tuf"
    path.mkdir()
    yield path
    shutil.rmtree(path, onerror=on_rm_error)


@fixture(autouse=True)
def repo_path(request, repo_dir):
    # Get the base directory path

    # Append the test name
    test_name = request.node.name
    full_path = repo_dir / test_name
    full_path.mkdir()

    # Convert to string if necessary, or use it as a Path object
    yield full_path
    shutil.rmtree(full_path, onerror=on_rm_error)


@fixture(scope="session", autouse=True)
def output_path():
    shutil.rmtree(TEST_OUTPUT_PATH, ignore_errors=True)
    TEST_OUTPUT_PATH.mkdir()
    yield TEST_OUTPUT_PATH
    shutil.rmtree(TEST_OUTPUT_PATH, onerror=on_rm_error)


@fixture
def client_dir():
    return CLIENT_DIR_PATH


@fixture
def origin_dir():
    return TEST_DATA_ORIGIN_PATH


@fixture
def keystore():
    """Keystore path."""
    return str(KEYSTORE_PATH)


@fixture
def wrong_keystore():
    """Path of the wrong keystore"""
    return str(WRONG_KEYSTORE_PATH)
