from pathlib import Path

import pytest
from yubikit.piv import SLOT

import taf.api.yubikey as yk_api
import taf.yubikey.yubikey as yk
from taf.exceptions import YubikeyError
from taf.yubikey.yubikey_manager import PinManager

KEYSTORE_PATH = Path(__file__).parents[2] / "data" / "keystores" / "keystore"


def test_resolve_setup_slot_rejects_retired_slots():
    with pytest.raises(YubikeyError):
        yk_api._resolve_setup_slot("RETIRED1")


def test_get_slot_status_reports_signature_occupied_and_others_free(fake_yubikey):
    status = yk.get_slot_status(serial=fake_yubikey.serial)

    slot_status = status[fake_yubikey.serial]
    assert slot_status[SLOT.SIGNATURE] is not None
    assert slot_status[SLOT.AUTHENTICATION] is None
    assert slot_status[SLOT.KEY_MANAGEMENT] is None


def test_get_piv_public_keys_tuf_covers_every_occupied_slot(fake_yubikey):
    new_key_pem = (KEYSTORE_PATH / "root2").read_bytes()
    yk.setup(
        pin="123456",
        serial=fake_yubikey.serial,
        cert_cn="Second key",
        private_key_pem=new_key_pem,
        slot=SLOT.AUTHENTICATION,
    )

    keys = yk.get_piv_public_keys_tuf(serial=fake_yubikey.serial)[fake_yubikey.serial]

    assert set(keys.keys()) == {SLOT.SIGNATURE, SLOT.AUTHENTICATION}
    assert keys[SLOT.SIGNATURE].keyid == fake_yubikey.tuf_key.public_key.keyid
    # the two slots must resolve to two different keys
    assert keys[SLOT.SIGNATURE].keyid != keys[SLOT.AUTHENTICATION].keyid


def test_setup_into_free_slot_does_not_touch_existing_key(fake_yubikey):
    new_key_pem = (KEYSTORE_PATH / "root2").read_bytes()

    yk.setup(
        pin="123456",
        serial=fake_yubikey.serial,
        cert_cn="Second key",
        private_key_pem=new_key_pem,
        slot=SLOT.AUTHENTICATION,
    )

    status = yk.get_slot_status(serial=fake_yubikey.serial)[fake_yubikey.serial]
    assert status[SLOT.AUTHENTICATION] is not None
    # the original SIGNATURE key must be untouched, since we didn't reset
    assert status[SLOT.SIGNATURE] is not None
    original_cert = status[SLOT.SIGNATURE]
    assert (
        original_cert.public_key().public_numbers()
        == fake_yubikey.pub_key.public_numbers()
    )


def test_setup_refuses_to_overwrite_occupied_slot_without_force(fake_yubikey):
    with pytest.raises(YubikeyError):
        yk.setup(
            pin="123456",
            serial=fake_yubikey.serial,
            cert_cn="Should not be written",
            slot=SLOT.SIGNATURE,
            reset=False,
        )


def test_setup_overwrites_occupied_slot_with_force(fake_yubikey):
    new_key_pem = (KEYSTORE_PATH / "root2").read_bytes()

    yk.setup(
        pin="123456",
        serial=fake_yubikey.serial,
        cert_cn="Replacement key",
        private_key_pem=new_key_pem,
        slot=SLOT.SIGNATURE,
        reset=False,
        force=True,
    )

    status = yk.get_slot_status(serial=fake_yubikey.serial)[fake_yubikey.serial]
    new_cert = status[SLOT.SIGNATURE]
    assert (
        new_cert.public_key().public_numbers() != fake_yubikey.pub_key.public_numbers()
    )


def test_setup_signing_yubikey_can_write_signature_slot_without_resetting(
    fake_yubikey, monkeypatch
):
    monkeypatch.setattr(yk_api.click, "confirm", lambda *args, **kwargs: True)
    monkeypatch.setattr(yk, "export_yk_certificate", lambda *args, **kwargs: None)
    monkeypatch.setattr("builtins.input", lambda prompt="": "New signer")

    # SIGNATURE is already occupied by the fixture's default key, so
    # force=True is required, exactly like any other non-reset overwrite.
    yk_api.setup_signing_yubikey(
        PinManager(), key_size=2048, slot="SIGNATURE", reset=False, force=True
    )

    status = yk.get_slot_status(serial=fake_yubikey.serial)[fake_yubikey.serial]
    new_cert = status[SLOT.SIGNATURE]
    assert (
        new_cert.public_key().public_numbers() != fake_yubikey.pub_key.public_numbers()
    )


def test_setup_test_yubikey_declining_occupied_slot_confirmation_leaves_key_untouched(
    fake_yubikey, monkeypatch
):
    monkeypatch.setattr(yk_api.click, "confirm", lambda *args, **kwargs: False)

    new_key_path = KEYSTORE_PATH / "root2"

    yk_api.setup_test_yubikey(PinManager(), str(new_key_path))

    status = yk.get_slot_status(serial=fake_yubikey.serial)[fake_yubikey.serial]
    original_cert = status[SLOT.SIGNATURE]
    assert (
        original_cert.public_key().public_numbers()
        == fake_yubikey.pub_key.public_numbers()
    )


def test_setup_test_yubikey_force_skips_occupied_slot_confirmation(fake_yubikey):
    # force=True on an already-occupied slot must succeed without any
    # interactive confirmation, so click.confirm is deliberately left
    # unmocked here.
    new_key_path = KEYSTORE_PATH / "root2"

    yk_api.setup_test_yubikey(PinManager(), str(new_key_path), force=True)

    status = yk.get_slot_status(serial=fake_yubikey.serial)[fake_yubikey.serial]
    new_cert = status[SLOT.SIGNATURE]
    assert (
        new_cert.public_key().public_numbers() != fake_yubikey.pub_key.public_numbers()
    )


def test_setup_test_yubikey_explicit_reset_wipes_other_slots(fake_yubikey, monkeypatch):
    monkeypatch.setattr(yk_api.click, "confirm", lambda *args, **kwargs: True)

    new_key_path = KEYSTORE_PATH / "root2"

    yk_api.setup_test_yubikey(PinManager(), str(new_key_path), reset=True)

    status = yk.get_slot_status(serial=fake_yubikey.serial)[fake_yubikey.serial]
    new_cert = status[SLOT.SIGNATURE]
    assert (
        new_cert.public_key().public_numbers() != fake_yubikey.pub_key.public_numbers()
    )
    assert status[SLOT.AUTHENTICATION] is None
