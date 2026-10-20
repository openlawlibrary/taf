"""Unit tests for `_resolve_key_id_pins` in `taf.api.api_workflow`."""

import pytest
from yubikit.piv import SLOT

import taf.api.api_workflow as api_workflow
import taf.yubikey.yubikey as yk
from taf.exceptions import TAFError
from taf.tuf.keys import _get_legacy_keyid


def test_no_yubikeys_inserted_raises(monkeypatch, auth_repo):
    monkeypatch.setattr(yk, "get_serial_nums", lambda: [])

    with pytest.raises(TAFError):
        api_workflow._resolve_key_id_pins(auth_repo, ["targets"], "111111")


def test_single_yubikey_valid_for_role_binds_pin(
    monkeypatch, auth_repo, real_public_key
):
    targets_key = real_public_key("targets1")
    monkeypatch.setattr(yk, "get_serial_nums", lambda: [1])
    monkeypatch.setattr(
        yk,
        "get_piv_public_keys_tuf",
        lambda serial: {serial: {SLOT.SIGNATURE: targets_key}},
    )

    result = api_workflow._resolve_key_id_pins(auth_repo, ["targets"], "111111")

    assert result == {_get_legacy_keyid(targets_key): "111111"}


def test_multiple_yubikeys_only_one_valid_binds_pin_no_error(
    monkeypatch, auth_repo, real_public_key
):
    """The core bug fix: several YubiKeys inserted, only one of them is a
    valid signing key for the role(s) being loaded -> pin is bound to that
    one key, no TAFError is raised."""
    root_key = real_public_key("root1")
    targets_key = real_public_key("targets1")
    unrelated_key = real_public_key("delegated_role1")
    serial_to_keys = {
        1: {SLOT.SIGNATURE: root_key},
        2: {SLOT.SIGNATURE: targets_key},
        3: {SLOT.SIGNATURE: unrelated_key},
    }

    monkeypatch.setattr(yk, "get_serial_nums", lambda: [1, 2, 3])
    monkeypatch.setattr(
        yk, "get_piv_public_keys_tuf", lambda serial: {serial: serial_to_keys[serial]}
    )

    result = api_workflow._resolve_key_id_pins(auth_repo, ["targets"], "222222")

    assert result == {_get_legacy_keyid(targets_key): "222222"}


def test_multiple_yubikeys_multiple_valid_returns_empty_and_warns(
    monkeypatch, auth_repo, real_public_key
):
    targets1_key = real_public_key("targets1")
    targets2_key = real_public_key("targets2")
    serial_to_keys = {
        1: {SLOT.SIGNATURE: targets1_key},
        2: {SLOT.SIGNATURE: targets2_key},
    }

    monkeypatch.setattr(yk, "get_serial_nums", lambda: [1, 2])
    monkeypatch.setattr(
        yk, "get_piv_public_keys_tuf", lambda serial: {serial: serial_to_keys[serial]}
    )

    result = api_workflow._resolve_key_id_pins(auth_repo, ["targets"], "333333")

    assert result == {}


def test_single_yubikey_not_valid_for_role_returns_empty_and_warns(
    monkeypatch, auth_repo, real_public_key
):
    unrelated_key = real_public_key("delegated_role1")

    monkeypatch.setattr(yk, "get_serial_nums", lambda: [1])
    monkeypatch.setattr(
        yk,
        "get_piv_public_keys_tuf",
        lambda serial: {serial: {SLOT.SIGNATURE: unrelated_key}},
    )

    result = api_workflow._resolve_key_id_pins(auth_repo, ["targets"], "444444")

    assert result == {}


def test_unreadable_yubikey_is_skipped_others_still_resolved(
    monkeypatch, auth_repo, real_public_key
):
    targets_key = real_public_key("targets1")

    def fake_get_piv_public_keys_tuf(serial):
        if serial == 1:
            raise Exception("card error")
        return {serial: {SLOT.SIGNATURE: targets_key}}

    monkeypatch.setattr(yk, "get_serial_nums", lambda: [1, 2])
    monkeypatch.setattr(yk, "get_piv_public_keys_tuf", fake_get_piv_public_keys_tuf)

    result = api_workflow._resolve_key_id_pins(auth_repo, ["targets"], "555555")

    assert result == {_get_legacy_keyid(targets_key): "555555"}


def test_single_yubikey_two_valid_slots_binds_pin_to_both_not_ambiguous(
    monkeypatch, auth_repo, real_public_key
):
    """A single physical YubiKey uses one PIN for every PIV slot, so finding
    two valid signing keys on it (one per slot) must not be treated as
    ambiguous - the pin is bound to both keyids."""
    root1_key = real_public_key("root1")
    root2_key = real_public_key("root2")

    monkeypatch.setattr(yk, "get_serial_nums", lambda: [1])
    monkeypatch.setattr(
        yk,
        "get_piv_public_keys_tuf",
        lambda serial: {
            serial: {SLOT.SIGNATURE: root1_key, SLOT.AUTHENTICATION: root2_key}
        },
    )

    result = api_workflow._resolve_key_id_pins(auth_repo, ["root"], "777777")

    assert result == {
        _get_legacy_keyid(root1_key): "777777",
        _get_legacy_keyid(root2_key): "777777",
    }


def test_key_on_non_signature_slot_still_resolved(
    monkeypatch, auth_repo, real_public_key
):
    """A valid signing key sitting in a non-SIGNATURE PIV slot must still be
    found - _resolve_key_id_pins should not assume SIGNATURE is the only
    occupied slot."""
    targets_key = real_public_key("targets1")

    monkeypatch.setattr(yk, "get_serial_nums", lambda: [1])
    monkeypatch.setattr(
        yk,
        "get_piv_public_keys_tuf",
        lambda serial: {serial: {SLOT.AUTHENTICATION: targets_key}},
    )

    result = api_workflow._resolve_key_id_pins(auth_repo, ["targets"], "666666")

    assert result == {_get_legacy_keyid(targets_key): "666666"}
