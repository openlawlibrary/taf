import pytest

import taf.yubikey.yubikey as yk
from taf.exceptions import SigningError
from taf.signer_loaders import (
    InputNeeded,
    KeystoreSignerLoader,
    load_role_signers,
    load_signers,
)
from taf.tests.tuf.test_keys.conftest import (
    RecordingLoader,
    pin_manager_for,
    write_signing_keystore,
)
from taf.tools.yubikey.yubikey_utils import _yk_piv_ctrl_mock
from taf.tuf.signer_uris import import_keystore_signer
from taf.constants import DEFAULT_RSA_SIGNATURE_SCHEME

ROOT_KEYS = ("root1", "root2", "root3")


def test_load_signers_loads_every_keystore_key_of_role(
    create_delegated_auth_repo, keystore_delegations, real_public_key, block_reprompt
):
    auth_repo = create_delegated_auth_repo()

    signers = load_signers(auth_repo, "root", keystore=str(keystore_delegations))

    assert {signer.public_key.keyid for signer in signers} == {
        real_public_key(name).keyid for name in ROOT_KEYS
    }


@pytest.mark.parametrize("first_file_holds", ["targets1", "root2"])
def test_load_signers_uses_remaining_keystore_files_when_first_one_is_not_usable(
    create_delegated_auth_repo,
    keystore_delegations,
    real_public_key,
    block_reprompt,
    tmp_path,
    first_file_holds,
):
    auth_repo = create_delegated_auth_repo()
    signing_keystore = write_signing_keystore(
        tmp_path,
        keystore_delegations,
        {"root1": first_file_holds, "root2": "root2", "root3": "root3"},
    )

    signers = load_signers(auth_repo, "root", keystore=str(signing_keystore))

    assert {signer.public_key.keyid for signer in signers} == {
        real_public_key(name).keyid for name in ("root2", "root3")
    }


def test_load_signers_adds_key_of_inserted_yubikey_without_asking_to_use_yubikeys(
    create_delegated_auth_repo,
    make_fake_yubikey,
    keystore_delegations,
    real_public_key,
    declined_prompts,
    tmp_path,
):
    device = make_fake_yubikey("root2", keystore_path=keystore_delegations)
    auth_repo = create_delegated_auth_repo(pin_manager_for(device))
    signing_keystore = write_signing_keystore(tmp_path, keystore_delegations, ["root1"])

    signers = load_signers(auth_repo, "root", keystore=str(signing_keystore))

    assert {signer.public_key.keyid for signer in signers} == {
        real_public_key(name).keyid for name in ("root1", "root2")
    }
    assert declined_prompts == [
        "Threshold of root keys reached. Do you want to load more root keys? [y/N]"
    ]


def test_load_signers_raises_when_keys_are_missing_and_user_declines_yubikeys(
    create_delegated_auth_repo,
    keystore_delegations,
    declined_prompts,
    tmp_path,
    monkeypatch,
):
    monkeypatch.setattr(yk, "_yk_piv_ctrl", _yk_piv_ctrl_mock)
    auth_repo = create_delegated_auth_repo()
    signing_keystore = write_signing_keystore(tmp_path, keystore_delegations, ["root1"])

    with pytest.raises(SigningError, match="Cannot load keys of role root"):
        load_signers(auth_repo, "root", keystore=str(signing_keystore))
    assert declined_prompts == ["Sign root using YubiKey(s)?"]


def test_load_role_signers_tries_loaders_by_priority_and_stops_at_threshold(
    create_delegated_auth_repo, keystore_delegations, real_public_key, block_reprompt
):
    auth_repo = create_delegated_auth_repo()
    calls = []
    device_loader = RecordingLoader("device", 5, InputNeeded.DEVICE, [], calls)
    second_file_loader = RecordingLoader(
        "second file",
        1,
        InputNeeded.NONE,
        [
            import_keystore_signer(
                keystore_delegations, "root2", DEFAULT_RSA_SIGNATURE_SCHEME
            )
        ],
        calls,
    )
    keystore_loader = KeystoreSignerLoader(None)
    first_file_loader = RecordingLoader(
        "first file",
        0,
        InputNeeded.NONE,
        [
            import_keystore_signer(
                keystore_delegations, "root1", DEFAULT_RSA_SIGNATURE_SCHEME
            )
        ],
        calls,
    )

    signers = load_role_signers(
        auth_repo,
        "root",
        [device_loader, second_file_loader, keystore_loader, first_file_loader],
    )

    assert calls == ["first file", "second file"]
    assert {signer.public_key.keyid for signer in signers} == {
        real_public_key(name).keyid for name in ("root1", "root2")
    }
