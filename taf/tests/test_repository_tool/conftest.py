import taf.repository_tool as repository_tool
from pytest import fixture
from securesystemslib.interface import (
    import_rsa_privatekey_from_file,
    import_rsa_publickey_from_file,
)
from taf.repository_tool import Repository
from taf.tests.yubikey_utils import (
    Root1YubiKey,
    Root2YubiKey,
    Root3YubiKey,
    TargetYubiKey,
)
from taf.tests.conftest import TEST_DATA_PATH, origin_repos_group

KEYSTORES_PATH = TEST_DATA_PATH / "keystores"
KEYSTORE_PATH = KEYSTORES_PATH / "keystore"
WRONG_KEYSTORE_PATH = KEYSTORES_PATH / "wrong_keystore"
DELEGATED_ROLES_KEYSTORE_PATH = KEYSTORES_PATH / "delegated_roles_keystore"
HANDLERS_DATA_INPUT_DIR = TEST_DATA_PATH / "handler_inputs"


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


@fixture(scope="session", autouse=True)
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


@fixture
def targets_key(pytestconfig):
    """Targets key."""
    return _load_key(KEYSTORE_PATH, "targets", pytestconfig.option.signature_scheme)


@fixture
def delegated_role11_key(pytestconfig):
    return _load_key(
        DELEGATED_ROLES_KEYSTORE_PATH,
        "delegated_role11",
        pytestconfig.option.signature_scheme,
    )


@fixture
def delegated_role12_key(pytestconfig):
    return _load_key(
        DELEGATED_ROLES_KEYSTORE_PATH,
        "delegated_role12",
        pytestconfig.option.signature_scheme,
    )


@fixture
def delegated_role13_key(pytestconfig):
    return _load_key(
        DELEGATED_ROLES_KEYSTORE_PATH,
        "delegated_role13",
        pytestconfig.option.signature_scheme,
    )


@fixture
def delegated_role2_key(pytestconfig):
    return _load_key(
        DELEGATED_ROLES_KEYSTORE_PATH,
        "delegated_role2",
        pytestconfig.option.signature_scheme,
    )


@fixture
def inner_delegated_role_key(pytestconfig):
    return _load_key(
        DELEGATED_ROLES_KEYSTORE_PATH,
        "inner_delegated_role",
        pytestconfig.option.signature_scheme,
    )
