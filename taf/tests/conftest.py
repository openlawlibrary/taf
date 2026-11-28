from taf.yubikey.yubikey_manager import PinManager
import pytest
import json
import re
import shutil
from pathlib import Path
from typing import Dict, Optional, Union

from taf.api.repository import create_repository
from taf.auth_repo import AuthenticationRepository
from taf.signers.keystore import create_signer_from_keystore_file

# from taf.tests import TEST_WITH_REAL_YK
from taf.utils import on_rm_error
from taf.constants import DEFAULT_RSA_SIGNATURE_SCHEME

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
REPOSITORY_DESCRIPTION_INPUT_DIR = TEST_DATA_PATH / "repository_description_inputs"
NO_YUBIKEYS_INPUT = REPOSITORY_DESCRIPTION_INPUT_DIR / "no_yubikeys.json"
KEYSTORE_NO_YUBIKEYS_INPUT = (
    REPOSITORY_DESCRIPTION_INPUT_DIR / "keystore_no_yubikeys.json"
)
WITH_DELEGATIONS_NO_YUBIKEY = (
    REPOSITORY_DESCRIPTION_INPUT_DIR / "with_delegations_no_yubikeys.json"
)
DELEGATION_PATHS_INPUT = REPOSITORY_DESCRIPTION_INPUT_DIR / "delegation_paths.json"
REPOSITORIES_JSON_PATH = TEST_INIT_DATA_PATH / "repositories.json"
MIRRORS_JSON_PATH = TEST_INIT_DATA_PATH / "mirrors.json"


@pytest.fixture(scope="session", autouse=True)
def repo_dir():
    path = CLIENT_DIR_PATH
    if path.is_dir():
        shutil.rmtree(path, onerror=on_rm_error)
    path.mkdir(parents=True)
    yield path
    shutil.rmtree(path, onerror=on_rm_error)


@pytest.fixture(scope="session")
def keystore():
    """Create signer from some rsa test key."""
    return TEST_DATA_PATH / "keystores" / "keystore"


@pytest.fixture(scope="session")
def keystore_delegations():
    """Create signer from some rsa test key."""
    return TEST_DATA_PATH / "keystores" / "keystore_delegations"


def keys_description_of_scheme(scheme: str) -> Dict:
    """Keys description whose roles all use scheme, matching the keys of
    keystore_of_scheme"""
    return {
        "roles": {
            "root": {"number": 2, "threshold": 2, "scheme": scheme},
            "targets": {"scheme": scheme},
            "snapshot": {"scheme": scheme},
            "timestamp": {"scheme": scheme},
        }
    }


@pytest.fixture(scope="session")
def keystore_of_scheme():
    """Factory returning the keystore whose keys, those of
    keys_description_of_scheme, use the given scheme"""

    def _keystore(scheme: str) -> Path:
        return KEYSTORES_PATH / f"keystore_{scheme.replace('-', '_').replace('/', '_')}"

    return _keystore


@pytest.fixture(scope="session")
def empty_keystore():
    return KEYSTORES_PATH / "empty_keystore"


@pytest.fixture(scope="session")
def keystore_delegations_root1():
    """Only the root1 key of keystore_delegations"""
    return KEYSTORES_PATH / "keystore_delegations_root1"


@pytest.fixture
def keystore_password_protected_key(tmp_path):
    """Copy of a keystore with a password-protected key of new_role, written by
    an older taf version. A test that writes to it can't change the committed
    files"""
    keystore = tmp_path / "keystore_password_protected_key"
    shutil.copytree(KEYSTORES_PATH / "keystore_password_protected_key", keystore)
    return keystore


@pytest.fixture(scope="session")
def keystore_delegations_snapshot_timestamp():
    """Only the snapshot and timestamp keys of keystore_delegations"""
    return KEYSTORES_PATH / "keystore_delegations_snapshot_timestamp"


@pytest.fixture(scope="session")
def keystore_rsassa_pss_sha256_snapshot_timestamp():
    """Only the snapshot and timestamp keys of the rsassa-pss-sha256 keystore"""
    return KEYSTORES_PATH / "keystore_rsassa_pss_sha256_snapshot_timestamp"


@pytest.fixture(
    params=["targets1", "root2"],
    ids=["root1 file holds a key of another role", "root1 file holds a copy of root2"],
)
def keystore_delegations_with_unusable_root1_file(request):
    """root1, root2 and root3 keys of keystore_delegations, but the root1 file
    holds another key"""
    return KEYSTORES_PATH / f"keystore_delegations_root1_holds_{request.param}"


@pytest.fixture(scope="session")
def real_public_key(keystore_delegations):
    """Factory returning the real public key of a named key file in keystore_delegations."""

    def _real_public_key(key_name):
        return create_signer_from_keystore_file(
            keystore_delegations, key_name, DEFAULT_RSA_SIGNATURE_SCHEME
        ).public_key

    return _real_public_key


@pytest.fixture(scope="session")
def mirrors_json_path():
    return MIRRORS_JSON_PATH


@pytest.fixture(scope="session")
def no_yubikeys_input():
    return json.loads(NO_YUBIKEYS_INPUT.read_text())


@pytest.fixture(scope="session")
def keystore_no_yubikeys_path():
    return str(KEYSTORE_NO_YUBIKEYS_INPUT)


@pytest.fixture(scope="session")
def with_delegations_no_yubikeys_input():
    return json.loads(WITH_DELEGATIONS_NO_YUBIKEY.read_text())


@pytest.fixture(scope="session")
def with_delegations_no_yubikeys_path():
    return WITH_DELEGATIONS_NO_YUBIKEY


@pytest.fixture(scope="session")
def delegation_paths_input():
    return json.loads(DELEGATION_PATHS_INPUT.read_text())


@pytest.fixture(scope="session")
def signers(keystore):
    return _load_signers_from_keystore(keystore)


@pytest.fixture(scope="session")
def signers_with_delegations(keystore_delegations):
    return _load_signers_from_keystore(keystore_delegations)


@pytest.fixture(scope="session")
def public_keys(signers):
    return {
        role_name: [signer.public_key for signer in signers]
        for role_name, signers in signers.items()
    }


@pytest.fixture(scope="session")
def public_keys_with_delegations(signers_with_delegations):
    return {
        role_name: [signer.public_key for signer in signers]
        for role_name, signers in signers_with_delegations.items()
    }


def _load_signers_from_keystore(keystore):
    def normalize_base_name(name):
        return re.sub(r"\d+$", "", name)

    signers = {}

    for file in keystore.iterdir():
        if file.is_file() and file.suffix == "":
            normalized_base_name = normalize_base_name(file.stem)

            if normalized_base_name not in signers:
                signers[normalized_base_name] = []
            signers[normalized_base_name].append(
                create_signer_from_keystore_file(
                    file.parent, file.name, DEFAULT_RSA_SIGNATURE_SCHEME
                )
            )
    return signers


@pytest.fixture(scope="session")
def repositories_json_template():
    return json.loads(Path(REPOSITORIES_JSON_PATH).read_text())


@pytest.fixture(autouse=True)
def repo_path(request, repo_dir):
    # Get the base directory path

    # Append the test name
    test_name = request.node.name
    full_path = repo_dir / test_name
    full_path.mkdir(parents=True)

    yield full_path
    shutil.rmtree(full_path, onerror=on_rm_error)


@pytest.fixture(scope="session", autouse=True)
def output_path():
    shutil.rmtree(TEST_OUTPUT_PATH, ignore_errors=True)
    TEST_OUTPUT_PATH.mkdir()
    yield TEST_OUTPUT_PATH
    shutil.rmtree(TEST_OUTPUT_PATH, onerror=on_rm_error)


@pytest.fixture(scope="session")
def pin_manager():
    return PinManager()


def create_authentication_repository(
    library_dir: Path,
    pin_manager: PinManager,
    repo_name: str,
    keys_description: Union[str, Dict],
    is_test_repo: bool = False,
    keystore: Optional[Path] = None,
) -> AuthenticationRepository:
    repo_path = Path(library_dir, repo_name)
    create_repository(
        str(repo_path),
        pin_manager,
        str(keystore) if keystore is not None else str(KEYSTORE_PATH),
        keys_description,
        commit=True,
        test=is_test_repo,
    )
    return AuthenticationRepository(library_dir, repo_name, pin_manager=pin_manager)


@pytest.fixture(scope="session")
def client_dir():
    return CLIENT_DIR_PATH


@pytest.fixture(scope="session")
def origin_dir():
    return TEST_DATA_ORIGIN_PATH


@pytest.fixture(scope="session")
def wrong_keystore():
    """Path of the wrong keystore"""
    return str(WRONG_KEYSTORE_PATH)
