import pytest

import taf.yubikey.yubikey as yk
from taf.exceptions import SigningError
from taf.signers.base import InputNeeded
from taf.signers.keystore import (
    KeystoreStorage,
    create_signer_from_keystore_file,
)
from taf.signers.loaders import load_role_signers, load_signers
from taf.tests.tuf.test_keys.conftest import FakeKeyStorage, pin_manager_for
from taf.tools.yubikey.yubikey_utils import _yk_piv_ctrl_mock
from taf.constants import DEFAULT_RSA_SIGNATURE_SCHEME


def test_load_signers_loads_every_keystore_key_of_role(
    create_delegated_auth_repo, keystore_delegations, real_public_key, block_reprompt
):
    auth_repo = create_delegated_auth_repo()

    signers = load_signers(auth_repo, "root", keystore=str(keystore_delegations))

    assert {signer.public_key.keyid for signer in signers} == {
        real_public_key(name).keyid for name in ("root1", "root2", "root3")
    }


def test_load_signers_uses_remaining_keystore_files_when_root1_file_is_not_usable(
    create_delegated_auth_repo,
    keystore_delegations_with_unusable_root1_file,
    real_public_key,
    block_reprompt,
):
    auth_repo = create_delegated_auth_repo()

    signers = load_signers(
        auth_repo, "root", keystore=str(keystore_delegations_with_unusable_root1_file)
    )

    assert {signer.public_key.keyid for signer in signers} == {
        real_public_key(name).keyid for name in ("root2", "root3")
    }


def test_load_signers_adds_key_of_inserted_yubikey_to_keystore_keys(
    create_delegated_auth_repo,
    make_fake_yubikey,
    keystore_delegations,
    keystore_delegations_root1,
    real_public_key,
    decline_prompts,
):
    device = make_fake_yubikey("root2", keystore_path=keystore_delegations)
    auth_repo = create_delegated_auth_repo(pin_manager_for(device))

    signers = load_signers(auth_repo, "root", keystore=str(keystore_delegations_root1))

    assert {signer.public_key.keyid for signer in signers} == {
        real_public_key(name).keyid for name in ("root1", "root2")
    }


def test_load_signers_raises_when_keys_are_missing_and_user_declines_yubikeys(
    create_delegated_auth_repo, keystore_delegations_root1, decline_prompts, monkeypatch
):
    monkeypatch.setattr(yk, "_yk_piv_ctrl", _yk_piv_ctrl_mock)
    auth_repo = create_delegated_auth_repo()

    with pytest.raises(SigningError, match="Cannot load keys of role root"):
        load_signers(auth_repo, "root", keystore=str(keystore_delegations_root1))


def test_load_role_signers_tries_storages_by_priority_and_stops_at_threshold(
    create_delegated_auth_repo, keystore_delegations, real_public_key, block_reprompt
):
    auth_repo = create_delegated_auth_repo()
    calls = []
    device_storage = FakeKeyStorage("device", 5, InputNeeded.DEVICE, [], calls)
    second_file_storage = FakeKeyStorage(
        "second file",
        1,
        InputNeeded.NONE,
        [
            create_signer_from_keystore_file(
                keystore_delegations, "root2", DEFAULT_RSA_SIGNATURE_SCHEME
            )
        ],
        calls,
    )
    keystore_storage = KeystoreStorage(auth_repo, None)
    first_file_storage = FakeKeyStorage(
        "first file",
        0,
        InputNeeded.NONE,
        [
            create_signer_from_keystore_file(
                keystore_delegations, "root1", DEFAULT_RSA_SIGNATURE_SCHEME
            )
        ],
        calls,
    )

    signers = load_role_signers(
        auth_repo,
        "root",
        [device_storage, second_file_storage, keystore_storage, first_file_storage],
    )

    assert calls == ["first file", "second file"]
    assert {signer.public_key.keyid for signer in signers} == {
        real_public_key(name).keyid for name in ("root1", "root2")
    }
