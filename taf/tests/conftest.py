from taf.yubikey.yubikey_manager import PinManager
import pytest
import json
import re
import shutil
from pathlib import Path

from taf.tuf.keys import load_signer_from_file

# from taf.tests import TEST_WITH_REAL_YK
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
REPOSITORY_DESCRIPTION_INPUT_DIR = TEST_DATA_PATH / "repository_description_inputs"
NO_YUBIKEYS_INPUT = REPOSITORY_DESCRIPTION_INPUT_DIR / "no_yubikeys.json"
WITH_DELEGATIONS_NO_YUBIKEY = (
    REPOSITORY_DESCRIPTION_INPUT_DIR / "with_delegations_no_yubikeys.json"
)
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


@pytest.fixture(scope="session")
def mirrors_json_path():
    return MIRRORS_JSON_PATH


@pytest.fixture(scope="session")
def no_yubikeys_input():
    return json.loads(NO_YUBIKEYS_INPUT.read_text())


@pytest.fixture(scope="session")
def with_delegations_no_yubikeys_input():
    return json.loads(WITH_DELEGATIONS_NO_YUBIKEY.read_text())


@pytest.fixture(scope="session")
def with_delegations_no_yubikeys_path():
    return WITH_DELEGATIONS_NO_YUBIKEY


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
            signers[normalized_base_name].append(load_signer_from_file(file))
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
