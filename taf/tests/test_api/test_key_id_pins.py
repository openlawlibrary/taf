"""Unit tests for `_resolve_key_id_pins` in `taf.api.api_workflow`.

These cover the behavior that lets `--key-pin` be used even when multiple
YubiKeys are inserted, as long as the PIN can be unambiguously associated
with one of them (i.e. exactly one inserted YubiKey is a valid signing key
for the roles being loaded).
"""

from unittest.mock import MagicMock

import pytest

import taf.api.api_workflow as api_workflow
import taf.yubikey.yubikey as yk
from taf.exceptions import TAFError
from taf.tuf.keys import _get_legacy_keyid


class FakeAuthRepo:
    """Minimal stand-in for AuthenticationRepository.

    `valid_for` maps a role name to the set of public keys (by identity)
    that are considered valid signing keys for that role.
    """

    def __init__(self, valid_for):
        self.valid_for = valid_for

    def is_valid_metadata_yubikey(self, role, public_key=None):
        return public_key in self.valid_for.get(role, set())


def _fake_public_key(name):
    # A distinct sentinel object per "key"; only used for identity comparisons
    # and passed through _get_legacy_keyid, which is monkeypatched in tests
    # that need a concrete keyid.
    return MagicMock(name=name)


def test_no_yubikeys_inserted_raises(monkeypatch):
    monkeypatch.setattr(yk, "get_serial_nums", lambda: [])
    auth_repo = FakeAuthRepo(valid_for={})

    with pytest.raises(TAFError):
        api_workflow._resolve_key_id_pins(auth_repo, ["targets"], "111111")


def test_single_yubikey_valid_for_role_binds_pin(monkeypatch):
    key = _fake_public_key("key-1234")
    monkeypatch.setattr(yk, "get_serial_nums", lambda: ["1234"])
    monkeypatch.setattr(
        yk, "get_piv_public_key_tuf", lambda serial: {"1234": key}[serial]
    )
    monkeypatch.setattr(
        api_workflow, "_get_legacy_keyid", lambda public_key: "keyid-1234"
    )
    auth_repo = FakeAuthRepo(valid_for={"targets": {key}})

    result = api_workflow._resolve_key_id_pins(auth_repo, ["targets"], "111111")

    assert result == {"keyid-1234": "111111"}


def test_multiple_yubikeys_only_one_valid_binds_pin_no_error(monkeypatch):
    """The core bug fix: several YubiKeys inserted, only one of them is a
    valid signing key for the role(s) being loaded -> pin is bound to that
    one key, no TAFError is raised."""
    key_a = _fake_public_key("key-a")
    key_b = _fake_public_key("key-b")
    key_c = _fake_public_key("key-c")
    serial_to_key = {"1": key_a, "2": key_b, "3": key_c}

    monkeypatch.setattr(yk, "get_serial_nums", lambda: ["1", "2", "3"])
    monkeypatch.setattr(
        yk, "get_piv_public_key_tuf", lambda serial: serial_to_key[serial]
    )
    monkeypatch.setattr(
        api_workflow,
        "_get_legacy_keyid",
        lambda public_key: {key_a: "keyid-a", key_b: "keyid-b", key_c: "keyid-c"}[
            public_key
        ],
    )
    # Only key_b is valid for "targets"
    auth_repo = FakeAuthRepo(valid_for={"targets": {key_b}})

    result = api_workflow._resolve_key_id_pins(auth_repo, ["targets"], "222222")

    assert result == {"keyid-b": "222222"}


def test_multiple_yubikeys_multiple_valid_returns_empty_and_warns(monkeypatch):
    key_a = _fake_public_key("key-a")
    key_b = _fake_public_key("key-b")
    serial_to_key = {"1": key_a, "2": key_b}

    monkeypatch.setattr(yk, "get_serial_nums", lambda: ["1", "2"])
    monkeypatch.setattr(
        yk, "get_piv_public_key_tuf", lambda serial: serial_to_key[serial]
    )
    # Both keys are valid for "targets" -> ambiguous
    auth_repo = FakeAuthRepo(valid_for={"targets": {key_a, key_b}})

    result = api_workflow._resolve_key_id_pins(auth_repo, ["targets"], "333333")

    assert result == {}


def test_single_yubikey_not_valid_for_role_returns_empty_and_warns(monkeypatch):
    key_a = _fake_public_key("key-a")

    monkeypatch.setattr(yk, "get_serial_nums", lambda: ["1"])
    monkeypatch.setattr(yk, "get_piv_public_key_tuf", lambda serial: key_a)
    # No roles valid for this key
    auth_repo = FakeAuthRepo(valid_for={})

    result = api_workflow._resolve_key_id_pins(auth_repo, ["targets"], "444444")

    assert result == {}


def test_unreadable_yubikey_is_skipped_others_still_resolved(monkeypatch):
    key_b = _fake_public_key("key-b")

    def fake_get_piv_public_key_tuf(serial):
        if serial == "1":
            raise Exception("card error")
        return key_b

    monkeypatch.setattr(yk, "get_serial_nums", lambda: ["1", "2"])
    monkeypatch.setattr(yk, "get_piv_public_key_tuf", fake_get_piv_public_key_tuf)
    monkeypatch.setattr(api_workflow, "_get_legacy_keyid", lambda public_key: "keyid-b")
    auth_repo = FakeAuthRepo(valid_for={"targets": {key_b}})

    result = api_workflow._resolve_key_id_pins(auth_repo, ["targets"], "555555")

    assert result == {"keyid-b": "555555"}


def test_get_legacy_keyid_still_importable():
    # sanity check the real helper is importable from where api_workflow expects it
    assert callable(_get_legacy_keyid)
