from collections import defaultdict
import json
import pytest
from taf.models.types import RolesKeysData
from taf.tests.test_api.conftest import REPOSITORY_DESCRIPTION_INPUT_DIR
from taf.tuf.keys import load_public_key_from_file, load_signer_from_file
from taf.tests.test_repository.test_repo import MetadataRepository
from taf.models.converter import from_dict

from taf.tests.tuf import TEST_DATA_PATH
NO_YUBIKEYS_INPUT = REPOSITORY_DESCRIPTION_INPUT_DIR / "no_yubikeys.json"

@pytest.fixture
def keystore():
    """Create signer from some rsa test key."""
    return TEST_DATA_PATH / "keystores" / "keystore"


@pytest.fixture
def no_yubikeys_input():
    return json.loads(NO_YUBIKEYS_INPUT.read_text())

@pytest.fixture
def tuf_repo(tmp_path, keystore, no_yubikeys_input ):
    # Create new metadata repository
    tuf_repo = MetadataRepository(tmp_path)
    roles_keys_data = from_dict(no_yubikeys_input, RolesKeysData)
    roles_keys_data.keystore = keystore
    signers, verification_keys = _load_keys_from_keystore(keystore)
    tuf_repo.create(roles_keys_data, signers, verification_keys)
    import pdb; pdb.set_trace()
    yield tuf_repo


def _load_keys_from_keystore(keystore):
    files = {}
    for file in keystore.iterdir():
        if file.is_file():
            base_name = file.stem
            extension = file.suffix

            # Store file information
            if base_name not in files:
                files[base_name] = []
            files[base_name].append((file, extension))

    signers = defaultdict(list)
    verification_keys = defaultdict(list)
    for base_name, items in files.items():
        priv_file = None
        pub_file = None
        for item in items:
            if item[1] == '':
                priv_file = item[0]
            elif item[1] == '.pub':
                pub_file = item[0]

        if priv_file and pub_file:
            verification_keys[base_name].append(load_public_key_from_file(keystore / f"{base_name}.pub"))
            signers[base_name].append(load_signer_from_file(keystore / base_name))
    return signers, verification_keys
