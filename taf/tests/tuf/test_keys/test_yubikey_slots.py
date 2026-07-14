import pytest
from yubikit.core import NotSupportedError
from yubikit.piv import DEFAULT_MANAGEMENT_KEY, SLOT

import taf.api.yubikey as yk_api
import taf.yubikey.yubikey as yk
from taf.exceptions import YubikeyError
from taf.tools.yubikey.yubikey_utils import FakePivController
from taf.yubikey.yubikey_manager import PinManager


def _pin_manager(fake_yubikey) -> PinManager:
    """A PinManager pre-populated with the fake device's PIN, matching a
    real caller that already knows it from an earlier interactive prompt."""
    pin_manager = PinManager()
    pin_manager.add_pin(fake_yubikey.serial, fake_yubikey.pin)
    return pin_manager


def test_resolve_slot_rejects_retired_slots():
    with pytest.raises(YubikeyError):
        yk_api._resolve_slot("RETIRED1")


def test_get_slot_status_reports_signature_occupied_and_others_free(fake_yubikey):
    status = yk.get_slot_status(serial=fake_yubikey.serial)

    slot_status = status[fake_yubikey.serial]
    assert (
        slot_status[SLOT.SIGNATURE].public_key().public_numbers()
        == fake_yubikey.pub_key.public_numbers()
    )
    assert slot_status[SLOT.AUTHENTICATION] is None
    assert slot_status[SLOT.KEY_MANAGEMENT] is None


def test_is_slot_occupied_detects_key_without_certificate(fake_yubikey):
    # a slot's key and certificate are separate objects - simulate one
    # holding a key but no certificate (e.g. an interrupted setup(), or a
    # slot provisioned by another tool) and confirm occupancy is still
    # detected, rather than relying on certificate presence alone
    fake_yubikey.slots[SLOT.AUTHENTICATION] = {
        "priv_key": fake_yubikey.priv_key,
        "pub_key": fake_yubikey.pub_key,
        "cert": None,
    }

    assert yk.is_slot_occupied(fake_yubikey.serial, SLOT.AUTHENTICATION)


def test_is_slot_occupied_falls_back_to_certificate_on_older_firmware(
    fake_yubikey, monkeypatch
):
    def _unsupported(self, slot):
        raise NotSupportedError("get_slot_metadata requires firmware 5.3+")

    monkeypatch.setattr(FakePivController, "get_slot_metadata", _unsupported)

    # SIGNATURE has both a key and a certificate (the fixture's default), so
    # the certificate-based fallback must still detect it as occupied
    assert yk.is_slot_occupied(fake_yubikey.serial, SLOT.SIGNATURE)


def test_setup_reset_randomizes_and_stores_protected_management_key(fake_yubikey):
    yk.setup(
        pin="654321",
        serial=fake_yubikey.serial,
        cert_cn="Reset key",
        reset=True,
    )

    # the management key must no longer be the well-known PIV default...
    assert fake_yubikey.management_key != DEFAULT_MANAGEMENT_KEY
    # ...and it must be recoverable with the PIN that was just set
    with yk._yk_piv_ctrl(serial=fake_yubikey.serial) as [(ctrl, _)]:
        ctrl.verify_pin("654321")
        assert yk._get_protected_management_key(ctrl) == fake_yubikey.management_key


def test_setup_non_reset_recovers_stored_management_key(fake_yubikey, keystore):
    # reset first, choosing a new PIN - this randomizes the management key
    # and stores it protected by that PIN
    yk.setup(
        pin="654321",
        serial=fake_yubikey.serial,
        cert_cn="Reset key",
        reset=True,
    )

    # a later non-reset call, using the same PIN, must recover the stored
    # (randomized, no longer default) management key on its own and
    # authenticate successfully with it - not the PIV default
    new_key_pem = (keystore / "root2").read_bytes()
    yk.setup(
        pin="654321",
        serial=fake_yubikey.serial,
        cert_cn="Second key",
        private_key_pem=new_key_pem,
        slot=SLOT.AUTHENTICATION,
        reset=False,
    )

    status = yk.get_slot_status(serial=fake_yubikey.serial)[fake_yubikey.serial]
    assert status[SLOT.AUTHENTICATION] is not None


def test_get_piv_public_keys_tuf_covers_every_occupied_slot(fake_yubikey, keystore):
    new_key_pem = (keystore / "root2").read_bytes()
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


def test_setup_into_free_slot_does_not_touch_existing_key(fake_yubikey, keystore):
    new_key_pem = (keystore / "root2").read_bytes()

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


def test_setup_overwrites_occupied_slot_with_force(fake_yubikey, keystore):
    new_key_pem = (keystore / "root2").read_bytes()

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
        _pin_manager(fake_yubikey),
        key_size=2048,
        slot="SIGNATURE",
        reset=False,
        force=True,
    )

    status = yk.get_slot_status(serial=fake_yubikey.serial)[fake_yubikey.serial]
    new_cert = status[SLOT.SIGNATURE]
    assert (
        new_cert.public_key().public_numbers() != fake_yubikey.pub_key.public_numbers()
    )


def test_setup_test_yubikey_declining_occupied_slot_confirmation_leaves_key_untouched(
    fake_yubikey, monkeypatch, keystore
):
    monkeypatch.setattr(yk_api.click, "confirm", lambda *args, **kwargs: False)

    new_key_path = keystore / "root2"

    yk_api.setup_test_yubikey(_pin_manager(fake_yubikey), str(new_key_path))

    status = yk.get_slot_status(serial=fake_yubikey.serial)[fake_yubikey.serial]
    original_cert = status[SLOT.SIGNATURE]
    assert (
        original_cert.public_key().public_numbers()
        == fake_yubikey.pub_key.public_numbers()
    )


def test_setup_test_yubikey_force_skips_occupied_slot_confirmation(
    fake_yubikey, keystore
):
    # force=True on an already-occupied slot must succeed without any
    # interactive confirmation, so click.confirm is deliberately left
    # unmocked here.
    new_key_path = keystore / "root2"

    yk_api.setup_test_yubikey(_pin_manager(fake_yubikey), str(new_key_path), force=True)

    status = yk.get_slot_status(serial=fake_yubikey.serial)[fake_yubikey.serial]
    new_cert = status[SLOT.SIGNATURE]
    assert (
        new_cert.public_key().public_numbers() != fake_yubikey.pub_key.public_numbers()
    )


def test_setup_test_yubikey_explicit_reset_wipes_other_slots(
    fake_yubikey, monkeypatch, keystore
):
    monkeypatch.setattr(yk_api.click, "confirm", lambda *args, **kwargs: True)

    new_key_path = keystore / "root2"

    yk_api.setup_test_yubikey(PinManager(), str(new_key_path), reset=True)

    status = yk.get_slot_status(serial=fake_yubikey.serial)[fake_yubikey.serial]
    new_cert = status[SLOT.SIGNATURE]
    assert (
        new_cert.public_key().public_numbers() != fake_yubikey.pub_key.public_numbers()
    )
    assert status[SLOT.AUTHENTICATION] is None
