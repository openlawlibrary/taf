import os
import shutil
from contextlib import contextmanager
from pathlib import Path

import taf.repository_tool as repository_tool
import taf.yubikey
import taf.repositoriesdb as repositoriesdb
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
KEYSTORES_PATH = TEST_DATA_PATH / "keystores"
KEYSTORE_PATH = KEYSTORES_PATH / "keystore"
WRONG_KEYSTORE_PATH = KEYSTORES_PATH / "wrong_keystore"
DELEGATED_ROLES_KEYSTORE_PATH = KEYSTORES_PATH / "delegated_roles_keystore"
CLIENT_DIR_PATH = TEST_DATA_REPOS_PATH / "client"


def pytest_configure(config):
    if not TEST_WITH_REAL_YK:
        taf.yubikey._yk_piv_ctrl = _yk_piv_ctrl_mock


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
                shutil.copytree(root, str(dst_path))
                (dst_path / "git").rename(dst_path / ".git")
                repo_rel_path = Path(repo_rel_path).as_posix()
                paths[repo_rel_path] = str(dst_path)
    return paths


def _load_key(keystore_path, key_name, scheme):
    """Load private and public keys of the given name"""
    key = import_rsa_publickey_from_file(
        str(keystore_path / f"{key_name}.pub"), scheme=scheme
    )
    priv_key = import_rsa_privatekey_from_file(
        str(keystore_path / key_name), scheme=scheme
    )
    key["keyval"]["private"] = priv_key["keyval"]["private"]
    return key


@yield_fixture(scope="session", autouse=True)
def repositories(request, pytestconfig):
    """TAF repositories for testing."""
    repository_tool.DISABLE_KEYS_CACHING = True

    scheme = request.param
    pytestconfig.option.signature_scheme = scheme
    if scheme not in ["rsassa-pss-sha256", "rsa-pkcs1v15-sha256"]:
        raise ValueError(f"Invalid test config. Invalid scheme: {scheme}")

    scheme_suffix = scheme.split("-")[1]
    test_dir = "test-repository-tool"
    with origin_repos_group(test_dir, scheme_suffix) as origins:
        yield {
            repo_name.rsplit("-", 1)[0]: Repository(
                repos_origin_paths["taf"], repo_name=repo_name
            )
            for repo_name, repos_origin_paths in origins.items()
        }


@yield_fixture(scope="session", autouse=True)
def updater_repositories():
    test_dir = "test-updater"
    with origin_repos_group(test_dir) as origins:
        yield origins


@yield_fixture(scope="session", autouse=True)
def repositoriesdb_test_repositories():
    test_dir = "test-repositoriesdb"
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
def delegated_roles_keystore():
    """Path of the keystore with keys of delegated roles"""
    return str(DELEGATED_ROLES_KEYSTORE_PATH)


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
    return _load_key(KEYSTORE_PATH, "snapshot", pytestconfig.option.signature_scheme)


@fixture
def timestamp_key(pytestconfig):
    """Timestamp key."""
    return _load_key(KEYSTORE_PATH, "timestamp", pytestconfig.option.signature_scheme)


@yield_fixture
def targets_key(pytestconfig):
    """Targets key."""
    return _load_key(KEYSTORE_PATH, "targets", pytestconfig.option.signature_scheme)


@yield_fixture
def delegated_role11_key(pytestconfig):
    return _load_key(
        DELEGATED_ROLES_KEYSTORE_PATH,
        "delegated_role11",
        pytestconfig.option.signature_scheme,
    )


@yield_fixture
def delegated_role12_key(pytestconfig):
    return _load_key(
        DELEGATED_ROLES_KEYSTORE_PATH,
        "delegated_role12",
        pytestconfig.option.signature_scheme,
    )


@yield_fixture
def delegated_role13_key(pytestconfig):
    return _load_key(
        DELEGATED_ROLES_KEYSTORE_PATH,
        "delegated_role13",
        pytestconfig.option.signature_scheme,
    )


@yield_fixture
def delegated_role2_key(pytestconfig):
    return _load_key(
        DELEGATED_ROLES_KEYSTORE_PATH,
        "delegated_role2",
        pytestconfig.option.signature_scheme,
    )


@yield_fixture
def inner_delegated_role_key(pytestconfig):
    return _load_key(
        DELEGATED_ROLES_KEYSTORE_PATH,
        "inner_delegated_role",
        pytestconfig.option.signature_scheme,
    )


@contextmanager
def load_repositories(auth_repo, **kwargs):
    repositoriesdb.load_repositories(auth_repo, **kwargs)
    yield
    repositoriesdb.clear_repositories_db()
