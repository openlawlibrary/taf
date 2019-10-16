import os
import shutil
from contextlib import contextmanager
from pathlib import Path

import taf.repository_tool as repository_tool
import taf.yubikey
from pytest import fixture, yield_fixture
from securesystemslib.interface import (
    import_rsa_privatekey_from_file,
    import_rsa_publickey_from_file,
)
from taf.repository_tool import Repository
from taf.tests import TEST_WITH_REAL_YK
from taf.tests.yubikey_utils import (
    Root1YubiKey,
    Root2YubiKey,
    Root3YubiKey,
    TargetYubiKey,
    _yk_piv_ctrl_mock,
)
from taf.utils import on_rm_error

TEST_DATA_PATH = Path(__file__).parent / "data"
TEST_DATA_REPOS_PATH = TEST_DATA_PATH / "repos"
TEST_DATA_ORIGIN_PATH = TEST_DATA_REPOS_PATH / "origin"
KEYSTORE_PATH = TEST_DATA_PATH / "keystore"
WRONG_KEYSTORE_PATH = TEST_DATA_PATH / "wrong_keystore"
CLIENT_DIR_PATH = TEST_DATA_REPOS_PATH / "client"


def pytest_configure(config):
    if not TEST_WITH_REAL_YK:
        taf.yubikey._yk_piv_ctrl = _yk_piv_ctrl_mock


def pytest_generate_tests(metafunc):
    if "taf_happy_path" in metafunc.fixturenames:
        # When running tests with real yubikey, use just rsa-pkcs1v15-sha256 scheme
        schemes = (
            ["rsa-pkcs1v15-sha256"]
            if TEST_WITH_REAL_YK
            else ["rsassa-pss-sha256", "rsa-pkcs1v15-sha256"]
        )
        metafunc.parametrize("taf_happy_path", schemes, indirect=True)


@contextmanager
def origin_repos_group(test_group_dir):
    all_paths = {}
    test_group_dir = str(TEST_DATA_REPOS_PATH / test_group_dir)
    for test_dir in os.scandir(test_group_dir):
        if test_dir.is_dir():
            all_paths[test_dir.name] = _copy_repos(test_dir.path, test_dir.name)

    yield all_paths

    for test_name in all_paths:
        test_dst_path = str(TEST_DATA_ORIGIN_PATH / test_name)
        shutil.rmtree(test_dst_path, onerror=on_rm_error)


@contextmanager
def origin_repos(test_name):
    """Coppies git repository from `data/repos/test-XYZ` to data/repos/origin/test-XYZ
  path and renames `git` to `.git` for each repository.
  """
    test_dir_path = str(TEST_DATA_REPOS_PATH / test_name)
    temp_paths = _copy_repos(test_dir_path, test_name)

    yield temp_paths

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
                shutil.copytree(root, str(dst_path))
                (dst_path / "git").rename(dst_path / ".git")
                repo_rel_path = Path(repo_rel_path).as_posix()
                paths[repo_rel_path] = str(dst_path)
    return paths


@yield_fixture(scope="session", autouse=True)
def taf_happy_path(request, pytestconfig):
    """TAF repository for testing."""
    repository_tool.DISABLE_KEYS_CACHING = True

    def _create_origin(test_dir, taf_repo_name="taf"):
        with origin_repos(test_dir) as origins:
            taf_repo_origin_path = origins[taf_repo_name]
            yield Repository(taf_repo_origin_path)

    scheme = request.param
    pytestconfig.option.signature_scheme = scheme

    if scheme == "rsassa-pss-sha256":
        yield from _create_origin("test-happy-path")
    elif scheme == "rsa-pkcs1v15-sha256":
        yield from _create_origin("test-happy-path-pkcs1v15")
    else:
        raise ValueError(f"Invalid test config. Invalid scheme: {scheme}")


@yield_fixture(scope="session", autouse=True)
def updater_repositories():
    test_dir = "test-updater"
    with origin_repos_group(test_dir) as origins:
        yield origins


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


@fixture
def targets_yk(pytestconfig):
    """Targets YubiKey."""
    return TargetYubiKey(KEYSTORE_PATH, pytestconfig.option.signature_scheme)


@fixture
def root1_yk(pytestconfig):
    """Root1 YubiKey."""
    return Root1YubiKey(KEYSTORE_PATH, pytestconfig.option.signature_scheme)


@fixture
def root2_yk(pytestconfig):
    """Root2 YubiKey."""
    return Root2YubiKey(KEYSTORE_PATH, pytestconfig.option.signature_scheme)


@fixture
def root3_yk(pytestconfig):
    """Root3 YubiKey."""
    return Root3YubiKey(KEYSTORE_PATH, pytestconfig.option.signature_scheme)


@fixture
def snapshot_key(pytestconfig):
    """Snapshot key."""
    key = import_rsa_publickey_from_file(
        str(KEYSTORE_PATH / "snapshot.pub"), scheme=pytestconfig.option.signature_scheme
    )
    priv_key = import_rsa_privatekey_from_file(
        str(KEYSTORE_PATH / "snapshot"), scheme=pytestconfig.option.signature_scheme
    )
    key["keyval"]["private"] = priv_key["keyval"]["private"]
    return key


@fixture
def timestamp_key(pytestconfig):
    """Timestamp key."""
    key = import_rsa_publickey_from_file(
        str(KEYSTORE_PATH / "timestamp.pub"),
        scheme=pytestconfig.option.signature_scheme,
    )
    priv_key = import_rsa_privatekey_from_file(
        str(KEYSTORE_PATH / "timestamp"), scheme=pytestconfig.option.signature_scheme
    )
    key["keyval"]["private"] = priv_key["keyval"]["private"]
    return key


@yield_fixture
def targets_key(pytestconfig):
    """Targets key."""
    key = import_rsa_publickey_from_file(
        str(KEYSTORE_PATH / "targets.pub"), scheme=pytestconfig.option.signature_scheme
    )
    priv_key = import_rsa_privatekey_from_file(
        str(KEYSTORE_PATH / "targets"), scheme=pytestconfig.option.signature_scheme
    )
    key["keyval"]["private"] = priv_key["keyval"]["private"]
    return key
