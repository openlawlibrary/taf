"""Regression tests for setting up a brand-new signing YubiKey via
``yubikey_prompt`` (the path used by ``taf yubikey setup-signing-key``).

These exercise the ``creating_new_key=True`` flow with ``taf_repo=None``,
which is how the standalone setup command calls into the prompt: there is no
authentication repository involved when provisioning a fresh key.
"""

import taf.yubikey.yubikey as yk
from taf.yubikey.yubikey import yubikey_prompt
from taf.yubikey.yubikey_manager import PinManager


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


def test_setup_new_yubikey_pin_is_not_validated_against_card(
    monkeypatch, fake_single_yubikey
):
    """The entered PIN is the *new* PIN to be written to the freshly reset card.

    Validating it against the card's current PIN would fail on every attempt
    and, once the retry counter hits zero, lock the key with
    ``InvalidPINError: No retries left. YubiKey locked.`` — exactly the error
    seen during ``setup-signing-key``. So ``is_valid_pin`` must not be called,
    and the PIN the user entered must be the one stored.
    """
    monkeypatch.setattr(yk, "get_pin_for", lambda *a, **k: "111111")

    # Simulate a card that rejects the PIN and reports no retries remaining.
    validate_calls = []

    def fake_is_valid_pin(pin, serial):
        validate_calls.append((pin, serial))
        return (False, 0)

    monkeypatch.setattr(yk, "is_valid_pin", fake_is_valid_pin)

    pin_manager = PinManager()
    result = yubikey_prompt(
        ["new Yubikey"],
        pin_manager=pin_manager,
        taf_repo=None,
        creating_new_key=True,
        retry_on_failure=False,
    )

    assert validate_calls == []  # the new PIN must never be validated/locked
    assert result[0][1] == "1234"
    assert pin_manager.get_pin("1234") == "111111"
