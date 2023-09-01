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


def pytest_generate_tests(metafunc):
    if "repositories" in metafunc.fixturenames:
        # When running tests with real yubikey, use just rsa-pkcs1v15-sha256 scheme
        schemes = (
            ["rsa-pkcs1v15-sha256"]
            if TEST_WITH_REAL_YK
            else ["rsassa-pss-sha256", "rsa-pkcs1v15-sha256"]
        )
        metafunc.parametrize("repositories", schemes, indirect=True)


@contextmanager
def origin_repos_group(test_group_dir, scheme_suffix=None):
    all_paths = {}
    test_group_dir = str(TEST_DATA_REPOS_PATH / test_group_dir)
    for test_dir in os.scandir(test_group_dir):
        if test_dir.is_dir():
            if (
                scheme_suffix is not None and test_dir.name.endswith(scheme_suffix)
            ) or scheme_suffix is None:
                all_paths[test_dir.name] = _copy_repos(test_dir.path, test_dir.name)

    yield all_paths

    for test_name in all_paths:
        test_dst_path = str(TEST_DATA_ORIGIN_PATH / test_name)
        shutil.rmtree(test_dst_path, onerror=on_rm_error)


def _copy_repos(test_dir_path, test_name):
    paths = {}
    for root, dirs, _ in os.walk(test_dir_path):
        for dir_name in dirs:
            if dir_name == "git":
                repo_rel_path = Path(root).relative_to(test_dir_path)
                dst_path = TEST_DATA_ORIGIN_PATH / test_name / repo_rel_path
                # convert dst_path to string in order to support python 3.5
                shutil.rmtree(dst_path, ignore_errors=True)
                shutil.copytree(root, str(dst_path))
                (dst_path / "git").rename(dst_path / ".git")
                repo_rel_path = Path(repo_rel_path).as_posix()
                paths[repo_rel_path] = str(dst_path)
    return paths


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
