from collections import defaultdict
import json
import re
import pytest
from taf.models.types import RolesKeysData
from taf.tests.test_api.conftest import REPOSITORY_DESCRIPTION_INPUT_DIR
from taf.tuf.keys import load_public_key_from_file, load_signer_from_file
from taf.tests.test_repository.test_repo import MetadataRepository
from taf.models.converter import from_dict

from taf.tests.tuf import TEST_DATA_PATH
NO_YUBIKEYS_INPUT = REPOSITORY_DESCRIPTION_INPUT_DIR / "no_yubikeys.json"
WITH_DELEGATIONS = REPOSITORY_DESCRIPTION_INPUT_DIR / "with_delegations_no_yubikeys.json"


@pytest.fixture
def keystore():
    """Create signer from some rsa test key."""
    return TEST_DATA_PATH / "keystores" / "keystore"

@pytest.fixture
def keystore_delegations():
    """Create signer from some rsa test key."""
    return TEST_DATA_PATH / "keystores" / "api_keystore"


@pytest.fixture
def no_yubikeys_input():
    return json.loads(NO_YUBIKEYS_INPUT.read_text())


@pytest.fixture
def with_delegations_no_yubikeys_input():
    return json.loads(WITH_DELEGATIONS.read_text())


@pytest.fixture
def signers(keystore):
    return _load_signers_from_keystore(keystore)


@pytest.fixture
def signers_with_delegations(keystore_delegations):
    return _load_signers_from_keystore(keystore_delegations)


@pytest.fixture
def tuf_repo(tmp_path, signers, no_yubikeys_input):
    # Create new metadata repository
    tuf_repo = MetadataRepository(tmp_path)
    roles_keys_data = from_dict(no_yubikeys_input, RolesKeysData)
    tuf_repo.create(roles_keys_data, signers)
    yield tuf_repo


@pytest.fixture
def tuf_repo_with_delegations(tmp_path, signers_with_delegations, with_delegations_no_yubikeys_input):
    # Create new metadata repository
    tuf_repo = MetadataRepository(tmp_path)
    roles_keys_data = from_dict(with_delegations_no_yubikeys_input, RolesKeysData)
    tuf_repo.create(roles_keys_data, signers_with_delegations)
    yield tuf_repo


def _load_signers_from_keystore(keystore):
    def normalize_base_name(name):
        return re.sub(r'\d+$', '', name)

    signers = {}

    for file in keystore.iterdir():
        if file.is_file() and file.suffix == "":
            normalized_base_name = normalize_base_name(file.stem)

            if normalized_base_name not in signers:
                signers[normalized_base_name] = []
            signers[normalized_base_name].append(load_signer_from_file(file))
    return signers
