"""Unit tests for `_resolve_key_id_pins` in `taf.api.api_workflow`."""

import pytest

import taf.api.api_workflow as api_workflow
import taf.yubikey.yubikey as yk
from taf.exceptions import TAFError
from taf.tuf.keys import _get_legacy_keyid, load_signer_from_file


def _real_public_key(keystore_delegations, key_name):
    return load_signer_from_file(keystore_delegations / key_name).public_key


def test_no_yubikeys_inserted_raises(monkeypatch, auth_repo):
    monkeypatch.setattr(yk, "get_serial_nums", lambda: [])

    with pytest.raises(TAFError):
        api_workflow._resolve_key_id_pins(auth_repo, ["targets"], "111111")


def test_single_yubikey_valid_for_role_binds_pin(
    monkeypatch, auth_repo, keystore_delegations
):
    targets_key = _real_public_key(keystore_delegations, "targets1")
    monkeypatch.setattr(yk, "get_serial_nums", lambda: ["1"])
    monkeypatch.setattr(
        yk, "get_piv_public_key_tuf", lambda serial: {"1": targets_key}[serial]
    )

    result = api_workflow._resolve_key_id_pins(auth_repo, ["targets"], "111111")

    assert result == {_get_legacy_keyid(targets_key): "111111"}


def test_multiple_yubikeys_only_one_valid_binds_pin_no_error(
    monkeypatch, auth_repo, keystore_delegations
):
    """The core bug fix: several YubiKeys inserted, only one of them is a
    valid signing key for the role(s) being loaded -> pin is bound to that
    one key, no TAFError is raised."""
    root_key = _real_public_key(keystore_delegations, "root1")
    targets_key = _real_public_key(keystore_delegations, "targets1")
    unrelated_key = _real_public_key(keystore_delegations, "delegated_role1")
    serial_to_key = {"1": root_key, "2": targets_key, "3": unrelated_key}

    monkeypatch.setattr(yk, "get_serial_nums", lambda: ["1", "2", "3"])
    monkeypatch.setattr(
        yk, "get_piv_public_key_tuf", lambda serial: serial_to_key[serial]
    )

    result = api_workflow._resolve_key_id_pins(auth_repo, ["targets"], "222222")

    assert result == {_get_legacy_keyid(targets_key): "222222"}


def test_multiple_yubikeys_multiple_valid_returns_empty_and_warns(
    monkeypatch, auth_repo, keystore_delegations
):
    # targets' threshold is 1 out of 2 keys, so both targets1 and targets2
    # are independently valid signing keys for "targets" -> ambiguous
    targets1_key = _real_public_key(keystore_delegations, "targets1")
    targets2_key = _real_public_key(keystore_delegations, "targets2")
    serial_to_key = {"1": targets1_key, "2": targets2_key}

    monkeypatch.setattr(yk, "get_serial_nums", lambda: ["1", "2"])
    monkeypatch.setattr(
        yk, "get_piv_public_key_tuf", lambda serial: serial_to_key[serial]
    )

    result = api_workflow._resolve_key_id_pins(auth_repo, ["targets"], "333333")

    assert result == {}


def test_single_yubikey_not_valid_for_role_returns_empty_and_warns(
    monkeypatch, auth_repo, keystore_delegations
):
    unrelated_key = _real_public_key(keystore_delegations, "delegated_role1")

    monkeypatch.setattr(yk, "get_serial_nums", lambda: ["1"])
    monkeypatch.setattr(yk, "get_piv_public_key_tuf", lambda serial: unrelated_key)

    result = api_workflow._resolve_key_id_pins(auth_repo, ["targets"], "444444")

    assert result == {}


def test_unreadable_yubikey_is_skipped_others_still_resolved(
    monkeypatch, auth_repo, keystore_delegations
):
    targets_key = _real_public_key(keystore_delegations, "targets1")

    def fake_get_piv_public_key_tuf(serial):
        if serial == "1":
            raise Exception("card error")
        return targets_key

    monkeypatch.setattr(yk, "get_serial_nums", lambda: ["1", "2"])
    monkeypatch.setattr(yk, "get_piv_public_key_tuf", fake_get_piv_public_key_tuf)

    result = api_workflow._resolve_key_id_pins(auth_repo, ["targets"], "555555")

    assert result == {_get_legacy_keyid(targets_key): "555555"}
