"""Regression tests for setting up a brand-new signing YubiKey via
``yubikey_prompt`` (the path used by ``taf yubikey setup-signing-key``).

These exercise the ``creating_new_key=True`` flow with ``taf_repo=None``,
which is how the standalone setup command calls into the prompt: there is no
authentication repository involved when provisioning a fresh key.
"""

import pytest

import taf.yubikey.yubikey as yk
from taf.yubikey.yubikey import yubikey_prompt
from taf.yubikey.yubikey_manager import PinManager


@pytest.fixture
def fake_single_yubikey(monkeypatch):
    """Pretend exactly one YubiKey (serial ``1234``) is inserted."""
    monkeypatch.setattr(yk, "get_serial_nums", lambda: ["1234"])


def test_setup_new_yubikey_without_taf_repo_does_not_crash(
    monkeypatch, fake_single_yubikey
):
    """Provisioning a new key has no auth repo, so taf_repo is None.

    Before the fix, ``_read_and_check_single_yubikey`` dereferenced
    ``taf_repo.path`` unconditionally and raised
    ``AttributeError: 'NoneType' object has no attribute 'path'``.
    """
    monkeypatch.setattr(yk, "get_pin_for", lambda *a, **k: "111111")
    # If the (separate) validate-against-card path runs, don't let it loop/lock.
    monkeypatch.setattr(yk, "is_valid_pin", lambda *a, **k: (True, None))

    pin_manager = PinManager()
    result = yubikey_prompt(
        ["new Yubikey"],
        pin_manager=pin_manager,
        taf_repo=None,
        creating_new_key=True,
        retry_on_failure=False,
    )

    # A YubiKey tuple (public_key, serial, key_name) is returned for serial 1234.
    assert result[0][1] == "1234"
