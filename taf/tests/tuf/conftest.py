import json
import re

import pytest
from taf.tests.test_api.conftest import REPOSITORY_DESCRIPTION_INPUT_DIR
from taf.tuf.keys import load_signer_from_file

from taf.tests.tuf import TEST_DATA_PATH
NO_YUBIKEYS_INPUT = REPOSITORY_DESCRIPTION_INPUT_DIR / "no_yubikeys.json"
WITH_DELEGATIONS = REPOSITORY_DESCRIPTION_INPUT_DIR / "with_delegations_no_yubikeys.json"



@pytest.fixture(scope="module")
def no_yubikeys_input():
    return json.loads(NO_YUBIKEYS_INPUT.read_text())


@pytest.fixture(scope="module")
def with_delegations_no_yubikeys_input():
    return json.loads(WITH_DELEGATIONS.read_text())


@pytest.fixture(scope="module")
def signers(keystore):
    return _load_signers_from_keystore(keystore)


@pytest.fixture(scope="module")
def signers_with_delegations(keystore_delegations):
    return _load_signers_from_keystore(keystore_delegations)


@pytest.fixture(scope="module")
def public_keys(signers):
    return {
        role_name: [signer.public_key for signer in signers] for role_name, signers in signers.items()
    }


@pytest.fixture(scope="module")
def public_keys_with_delegations(signers_with_delegations):
    return {
        role_name: [signer.public_key for signer in signers] for role_name, signers in signers_with_delegations.items()
    }


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
