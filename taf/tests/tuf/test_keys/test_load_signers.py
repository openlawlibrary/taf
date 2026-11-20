import json
import shutil

import click
import pytest

import taf.signer_loaders
import taf.yubikey.yubikey as yk
from taf.exceptions import SigningError
from taf.signer_loaders import (
    InputNeeded,
    KeystoreSignerLoader,
    SignerLoader,
    load_role_signers,
    load_signers,
)
from taf.tests.conftest import create_authentication_repository
from taf.tests.tuf.test_keys.conftest import pin_manager_for
from taf.tools.yubikey.yubikey_utils import _yk_piv_ctrl_mock
from taf.tuf.signer_uris import import_keystore_signer
from taf.yubikey.yubikey_manager import PinManager
from taf.constants import DEFAULT_RSA_SIGNATURE_SCHEME

ROOT_KEYS = ("root1", "root2", "root3")


@pytest.fixture
def create_root_repo(repo_path, keystore, tmp_path):
    """Factory for a repository whose root has three keys and a threshold of
    two, all generated from the shared keystore."""

    def _create(pin_manager=None):
        keys_description = tmp_path / "keys-description.json"
        keys_description.write_text(
            json.dumps(
                {
                    "roles": {
                        "root": {
                            "number": 3,
                            "threshold": 2,
                            "scheme": DEFAULT_RSA_SIGNATURE_SCHEME,
                        },
                        "targets": {"scheme": DEFAULT_RSA_SIGNATURE_SCHEME},
                        "snapshot": {"scheme": DEFAULT_RSA_SIGNATURE_SCHEME},
                        "timestamp": {"scheme": DEFAULT_RSA_SIGNATURE_SCHEME},
                    }
                }
            )
        )
        return create_authentication_repository(
            repo_path,
            pin_manager if pin_manager is not None else PinManager(),
            "test/auth",
            str(keys_description),
            is_test_repo=True,
            keystore=keystore,
        )

    return _create


@pytest.fixture
def no_prompts(monkeypatch):
    def _unexpected_prompt(message, *_args, **_kwargs):
        raise AssertionError(f"unexpected prompt: {message}")

    monkeypatch.setattr(click, "confirm", _unexpected_prompt)
    monkeypatch.setattr(taf.signer_loaders, "secret_yes_no_prompt", _unexpected_prompt)


def copy_keystore(keystore, tmp_path, names):
    signing_keystore = tmp_path / "signing_keystore"
    signing_keystore.mkdir()
    for name in names:
        shutil.copy(keystore / name, signing_keystore / name)
    return signing_keystore


def keyids_of(*names, keystore):
    return {
        import_keystore_signer(
            keystore, name, DEFAULT_RSA_SIGNATURE_SCHEME
        ).public_key.keyid
        for name in names
    }


def test_load_signers_loads_every_keystore_key_of_role(
    create_root_repo, keystore, no_prompts
):
    auth_repo = create_root_repo()

    signers = load_signers(auth_repo, "root", keystore=str(keystore))

    assert {signer.public_key.keyid for signer in signers} == keyids_of(
        *ROOT_KEYS, keystore=keystore
    )


@pytest.mark.parametrize("first_file_holds", ["targets", "root2"])
def test_load_signers_uses_remaining_keystore_files_when_first_one_is_not_usable(
    create_root_repo, keystore, tmp_path, no_prompts, first_file_holds
):
    auth_repo = create_root_repo()
    signing_keystore = copy_keystore(keystore, tmp_path, ROOT_KEYS)
    shutil.copy(keystore / first_file_holds, signing_keystore / "root1")

    signers = load_signers(auth_repo, "root", keystore=str(signing_keystore))

    assert {signer.public_key.keyid for signer in signers} == keyids_of(
        "root2", "root3", keystore=keystore
    )


def test_load_signers_adds_key_of_inserted_yubikey_without_asking_to_use_yubikeys(
    create_root_repo, make_fake_yubikey, keystore, tmp_path, monkeypatch
):
    device = make_fake_yubikey("root2")
    auth_repo = create_root_repo(pin_manager_for(device))
    signing_keystore = copy_keystore(keystore, tmp_path, ["root1"])
    load_more_prompts = []

    def _unexpected_confirm(message, *_args, **_kwargs):
        raise AssertionError(f"unexpected prompt: {message}")

    def _decline_loading_more(message):
        load_more_prompts.append(message)
        return False

    monkeypatch.setattr(click, "confirm", _unexpected_confirm)
    monkeypatch.setattr(
        taf.signer_loaders, "secret_yes_no_prompt", _decline_loading_more
    )

    signers = load_signers(auth_repo, "root", keystore=str(signing_keystore))

    assert {signer.public_key.keyid for signer in signers} == keyids_of(
        "root1", "root2", keystore=keystore
    )
    assert len(load_more_prompts) == 1


def test_load_signers_raises_when_keys_are_missing_and_user_declines_yubikeys(
    create_root_repo, keystore, tmp_path, monkeypatch
):
    monkeypatch.setattr(yk, "_yk_piv_ctrl", _yk_piv_ctrl_mock)
    auth_repo = create_root_repo()
    signing_keystore = copy_keystore(keystore, tmp_path, ["root1"])
    questions = []

    def _decline(message, *_args, **_kwargs):
        questions.append(message)
        return False

    monkeypatch.setattr(click, "confirm", _decline)

    with pytest.raises(SigningError, match="Cannot load keys of role root"):
        load_signers(auth_repo, "root", keystore=str(signing_keystore))
    assert questions == ["Sign root using YubiKey(s)?"]


class _RecordingLoader(SignerLoader):
    def __init__(self, name, priority, input_needed, signers, calls):
        self.name = name
        self.priority = priority
        self.input_needed = input_needed
        self._signers = signers
        self._calls = calls

    def load(self, role, keys, threshold_reached):
        self._calls.append(self.name)
        return self._signers


def test_load_role_signers_tries_loaders_by_priority_and_stops_at_threshold(
    create_root_repo, keystore, no_prompts
):
    auth_repo = create_root_repo()
    calls = []
    device_loader = _RecordingLoader("device", 5, InputNeeded.DEVICE, [], calls)
    second_file_loader = _RecordingLoader(
        "second file",
        1,
        InputNeeded.NONE,
        [import_keystore_signer(keystore, "root2", DEFAULT_RSA_SIGNATURE_SCHEME)],
        calls,
    )
    keystore_loader = KeystoreSignerLoader(None)
    first_file_loader = _RecordingLoader(
        "first file",
        0,
        InputNeeded.NONE,
        [import_keystore_signer(keystore, "root1", DEFAULT_RSA_SIGNATURE_SCHEME)],
        calls,
    )

    signers = load_role_signers(
        auth_repo,
        "root",
        [device_loader, second_file_loader, keystore_loader, first_file_loader],
    )

    assert calls == ["first file", "second file"]
    assert {signer.public_key.keyid for signer in signers} == keyids_of(
        "root1", "root2", keystore=keystore
    )
