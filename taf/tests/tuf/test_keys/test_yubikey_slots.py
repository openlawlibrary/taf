import secrets
from pathlib import Path
from typing import Optional
from unittest import mock

import pytest
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from ykman.piv import MANAGEMENT_KEY_TYPE, pivman_set_mgm_key
from yubikit.core import NotSupportedError
from yubikit.piv import SLOT

import taf.api.yubikey as yk_api
import taf.keys as taf_keys
import taf.yubikey.yubikey as yk
from taf.exceptions import KeystoreError, YubikeyError
from taf.tools.yubikey.yubikey_utils import FakePivController
from taf.tuf.keys import YkSigner, load_signer_from_file
from taf.yubikey.yubikey_manager import PinManager, YubiKeyStore


def _pin_manager(fake_yubikey) -> PinManager:
    """A PinManager pre-populated with the fake device's PIN, matching a
    real caller that already knows it from an earlier interactive prompt."""
    pin_manager = PinManager()
    pin_manager.add_pin(fake_yubikey.serial, fake_yubikey.pin)
    return pin_manager


class _MinimalTafRepo:
    """Stand-in for the parts of AuthenticationRepository that
    _read_and_check_yubikeys/_load_and_verify_yubikey need, so this can be
    tested without building a full repository on disk just to check
    role/key validity."""

    def __init__(
        self, key_names_by_keyid: dict, pin_manager: Optional[PinManager] = None
    ):
        self.path = Path.cwd()
        self.yubikey_store = YubiKeyStore()
        self.keys_name_mappings = dict(key_names_by_keyid)
        self.pin_manager = pin_manager if pin_manager is not None else PinManager()

    def is_valid_metadata_yubikey(self, role, public_key):
        return public_key is not None and public_key.keyid in self.keys_name_mappings


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


def test_setup_recovers_stored_management_key(fake_yubikey, keystore):
    # simulate a card that was previously set up (by another tool, or an
    # earlier taf version) with a randomized, PIN-protected management key -
    # setup() must recover it on its own and authenticate successfully with
    # it, not the PIV default
    new_mgm_key = secrets.token_bytes(24)
    with yk._yk_piv_ctrl(serial=fake_yubikey.serial) as [(ctrl, _)]:
        ctrl.verify_pin(fake_yubikey.pin)
        pivman_set_mgm_key(
            ctrl, new_mgm_key, MANAGEMENT_KEY_TYPE.TDES, store_on_device=True
        )
    assert fake_yubikey.management_key == new_mgm_key

    new_key_pem = (keystore / "root2").read_bytes()
    yk.setup(
        pin=fake_yubikey.pin,
        serial=fake_yubikey.serial,
        cert_cn="Second key",
        private_key_pem=new_key_pem,
        slot=SLOT.AUTHENTICATION,
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


def test_setup_refuses_to_overwrite_occupied_slot(fake_yubikey):
    with pytest.raises(YubikeyError):
        yk.setup(
            pin="123456",
            serial=fake_yubikey.serial,
            cert_cn="Should not be written",
            slot=SLOT.SIGNATURE,
        )

    # the original key must be untouched
    status = yk.get_slot_status(serial=fake_yubikey.serial)[fake_yubikey.serial]
    assert (
        status[SLOT.SIGNATURE].public_key().public_numbers()
        == fake_yubikey.pub_key.public_numbers()
    )


def test_setup_refuses_occupied_slot_without_verifying_pin(fake_yubikey, monkeypatch):
    # checking slot occupancy is an unauthenticated PIV read - an occupied
    # slot must be refused before the PIN is ever verified, so a doomed
    # attempt doesn't burn one of the card's limited PIN retries.
    # raise_yubikey_err would wrap *any* unexpected exception (including one
    # raised by this mock) into a YubikeyError too, so match on the expected
    # message specifically rather than just the exception type - otherwise
    # this would pass even if verify_pin actually got called.
    def _unexpected_verify_pin(self, pin):
        raise AssertionError("should not verify the PIN for an occupied slot")

    monkeypatch.setattr(FakePivController, "verify_pin", _unexpected_verify_pin)

    with pytest.raises(YubikeyError, match="already has a key"):
        yk.setup(
            pin="123456",
            serial=fake_yubikey.serial,
            cert_cn="Should not be written",
            slot=SLOT.SIGNATURE,
        )


def test_setup_signing_yubikey_refuses_occupied_slot_without_prompting(
    fake_yubikey, monkeypatch
):
    # SIGNATURE is already occupied by the fixture's default key - taf must
    # refuse outright. There's no overwrite/reset flow to confirm anymore,
    # so click.confirm must never even be called.
    def _unexpected_confirm(*args, **kwargs):
        raise AssertionError("should not prompt to overwrite an occupied slot")

    monkeypatch.setattr("builtins.input", lambda prompt="": "")

    with mock.patch("click.confirm", side_effect=_unexpected_confirm):
        with pytest.raises(YubikeyError):
            yk_api.setup_signing_yubikey(
                _pin_manager(fake_yubikey),
                key_size=2048,
                slot="SIGNATURE",
            )

    status = yk.get_slot_status(serial=fake_yubikey.serial)[fake_yubikey.serial]
    assert (
        status[SLOT.SIGNATURE].public_key().public_numbers()
        == fake_yubikey.pub_key.public_numbers()
    )


def test_setup_test_yubikey_refuses_occupied_slot_without_prompting_for_pin(
    fake_yubikey, keystore, monkeypatch
):
    # an empty PinManager means _prepare_setup would have to prompt for a
    # PIN via get_and_validate_pin if it got that far - it must not, since
    # checking slot occupancy needs no PIN at all (an unauthenticated PIV
    # read).
    def _unexpected_get_and_validate_pin(*args, **kwargs):
        raise AssertionError("should not prompt for a PIN for an occupied slot")

    monkeypatch.setattr(yk, "get_and_validate_pin", _unexpected_get_and_validate_pin)

    new_key_path = keystore / "root2"
    with pytest.raises(YubikeyError, match="already has a key"):
        yk_api.setup_test_yubikey(PinManager(), str(new_key_path))


def test_setup_test_yubikey_missing_key_file_raises_keystore_error(
    fake_yubikey, monkeypatch
):
    # a bad key path is a plain file error, not a YubiKey problem - and it
    # must be caught before ever resolving a device/prompting for a PIN.
    def _unexpected_get_and_validate_pin(*args, **kwargs):
        raise AssertionError("should not prompt for a PIN for a missing key file")

    monkeypatch.setattr(yk, "get_and_validate_pin", _unexpected_get_and_validate_pin)

    with pytest.raises(KeystoreError, match="does not exist"):
        yk_api.setup_test_yubikey(PinManager(), "/no/such/key/file")


def test_setup_test_yubikey_validates_pin_against_card(
    fake_yubikey, keystore, monkeypatch
):
    # the PIN entered here is always the card's existing PIN (taf never sets
    # a new one) - a wrong entry must be caught and retried against the
    # card itself, not silently accepted like a "choose a new secret"
    # confirm-by-retyping prompt would.
    wrong_then_right_pins = iter(["000000", fake_yubikey.pin])
    monkeypatch.setattr(yk, "get_pin_for", lambda *a, **k: next(wrong_then_right_pins))

    new_key_path = keystore / "root2"
    with mock.patch("click.confirm", return_value=True) as confirm:
        yk_api.setup_test_yubikey(
            PinManager(), str(new_key_path), slot="AUTHENTICATION"
        )
    confirm.assert_called_once()

    status = yk.get_slot_status(serial=fake_yubikey.serial)[fake_yubikey.serial]
    assert status[SLOT.AUTHENTICATION] is not None


def test_setup_test_yubikey_uses_pin_from_environment_variable(
    fake_yubikey, keystore, monkeypatch
):
    # _prepare_setup must go through the same env-var-then-validate PIN
    # flow used everywhere else a PIN is entered (_resolve_and_cache_pin),
    # not a partial reimplementation that skips the environment variable.
    monkeypatch.setenv(f"PIN_{fake_yubikey.serial}", fake_yubikey.pin)

    def _unexpected_prompt(*args, **kwargs):
        raise AssertionError("should not prompt - PIN available from environment")

    with mock.patch("click.prompt", side_effect=_unexpected_prompt), mock.patch(
        "taf.yubikey.yubikey.get_pin_for", side_effect=_unexpected_prompt
    ):
        new_key_path = keystore / "root2"
        yk_api.setup_test_yubikey(
            PinManager(), str(new_key_path), slot="AUTHENTICATION"
        )

    status = yk.get_slot_status(serial=fake_yubikey.serial)[fake_yubikey.serial]
    assert status[SLOT.AUTHENTICATION] is not None


def test_setup_test_yubikey_refuses_occupied_slot_without_prompting(
    fake_yubikey, keystore
):
    def _unexpected_confirm(*args, **kwargs):
        raise AssertionError("should not prompt to overwrite an occupied slot")

    new_key_path = keystore / "root2"
    with mock.patch("click.confirm", side_effect=_unexpected_confirm):
        with pytest.raises(YubikeyError):
            yk_api.setup_test_yubikey(_pin_manager(fake_yubikey), str(new_key_path))

    status = yk.get_slot_status(serial=fake_yubikey.serial)[fake_yubikey.serial]
    assert (
        status[SLOT.SIGNATURE].public_key().public_numbers()
        == fake_yubikey.pub_key.public_numbers()
    )


def test_sign_piv_rsa_pkcs1v15_uses_given_slot(fake_yubikey, keystore):
    new_key_pem = (keystore / "root2").read_bytes()
    yk.setup(
        pin="123456",
        serial=fake_yubikey.serial,
        cert_cn="Second key",
        private_key_pem=new_key_pem,
        slot=SLOT.AUTHENTICATION,
    )

    sig = yk.sign_piv_rsa_pkcs1v15(
        b"data", "123456", serial=fake_yubikey.serial, slot=SLOT.AUTHENTICATION
    )

    auth_priv_key = serialization.load_pem_private_key(
        new_key_pem, None, default_backend()
    )
    # signed with the AUTHENTICATION slot's key, not SIGNATURE's
    auth_priv_key.public_key().verify(sig, b"data", padding.PKCS1v15(), hashes.SHA256())
    with pytest.raises(InvalidSignature):
        fake_yubikey.pub_key.verify(sig, b"data", padding.PKCS1v15(), hashes.SHA256())


def test_read_and_check_yubikeys_finds_role_key_in_non_signature_slot(
    fake_yubikey, keystore
):
    new_key_pem = (keystore / "root2").read_bytes()
    yk.setup(
        pin="123456",
        serial=fake_yubikey.serial,
        cert_cn="Second key",
        private_key_pem=new_key_pem,
        slot=SLOT.AUTHENTICATION,
    )
    auth_key = load_signer_from_file(keystore / "root2").public_key
    taf_repo = _MinimalTafRepo({auth_key.keyid: "root2"})

    result = yk._read_and_check_yubikeys(
        role="root",
        taf_repo=taf_repo,
        pin_manager=_pin_manager(fake_yubikey),
        pin_confirm=False,
        pin_repeat=False,
        prompt_message=None,
        key_names=["root2"],
        retrying=False,
        hide_already_loaded_message=True,
        hide_threshold_message=True,
        key_id_pins=None,
    )

    assert len(result) == 1
    public_key, serial_num, key_name, slot = result[0]
    assert slot == SLOT.AUTHENTICATION
    assert public_key.keyid == auth_key.keyid

    # the discovered slot must actually be used to sign, not SIGNATURE
    signer = YkSigner(
        public_key, serial_num, lambda name: "123456", key_name, slot=slot
    )
    sig = signer.sign(b"hello").signature
    auth_priv_key = serialization.load_pem_private_key(
        new_key_pem, None, default_backend()
    )
    auth_priv_key.public_key().verify(
        bytes.fromhex(sig), b"hello", padding.PKCS1v15(), hashes.SHA256()
    )


def test_read_and_check_yubikeys_counts_every_valid_key_on_one_device(
    fake_yubikey, keystore
):
    # one physical device can hold 2 keys valid for the same role (one per
    # slot) - both must count toward that role's threshold, not just the
    # first one found
    new_key_pem = (keystore / "root2").read_bytes()
    yk.setup(
        pin="123456",
        serial=fake_yubikey.serial,
        cert_cn="Second key",
        private_key_pem=new_key_pem,
        slot=SLOT.AUTHENTICATION,
    )
    sig_key = fake_yubikey.tuf_key.public_key
    auth_key = load_signer_from_file(keystore / "root2").public_key
    taf_repo = _MinimalTafRepo({sig_key.keyid: "root1", auth_key.keyid: "root2"})

    result = yk._read_and_check_yubikeys(
        role="root",
        taf_repo=taf_repo,
        pin_manager=_pin_manager(fake_yubikey),
        pin_confirm=False,
        pin_repeat=False,
        prompt_message=None,
        key_names=["root1", "root2"],
        retrying=False,
        hide_already_loaded_message=True,
        hide_threshold_message=True,
        key_id_pins=None,
    )

    assert len(result) == 2
    found = {(entry[0].keyid, entry[3]) for entry in result}
    assert found == {
        (sig_key.keyid, SLOT.SIGNATURE),
        (auth_key.keyid, SLOT.AUTHENTICATION),
    }


def test_signs_correctly_with_each_key_when_multiple_slots_occupied(
    fake_yubikey, keystore
):
    # discovering 2 valid keys on one device is only half the story - each
    # one must actually sign with its own key when used, not get mixed up
    # with the other slot's key on the same physical device.
    new_key_pem = (keystore / "root2").read_bytes()
    yk.setup(
        pin="123456",
        serial=fake_yubikey.serial,
        cert_cn="Second key",
        private_key_pem=new_key_pem,
        slot=SLOT.AUTHENTICATION,
    )
    sig_key = fake_yubikey.tuf_key.public_key
    auth_key = load_signer_from_file(keystore / "root2").public_key
    taf_repo = _MinimalTafRepo({sig_key.keyid: "root1", auth_key.keyid: "root2"})

    result = yk._read_and_check_yubikeys(
        role="root",
        taf_repo=taf_repo,
        pin_manager=_pin_manager(fake_yubikey),
        pin_confirm=False,
        pin_repeat=False,
        prompt_message=None,
        key_names=["root1", "root2"],
        retrying=False,
        hide_already_loaded_message=True,
        hide_threshold_message=True,
        key_id_pins=None,
    )
    assert len(result) == 2

    auth_priv_key = serialization.load_pem_private_key(
        new_key_pem, None, default_backend()
    )
    payload = b"shared payload signed by both keys"
    signed_slots = set()
    for public_key, serial_num, key_name, slot in result:
        signer = YkSigner(
            public_key, serial_num, lambda name: "123456", key_name, slot=slot
        )
        sig = bytes.fromhex(signer.sign(payload).signature)

        correct_key = (
            fake_yubikey.pub_key
            if slot == SLOT.SIGNATURE
            else auth_priv_key.public_key()
        )
        wrong_key = (
            auth_priv_key.public_key()
            if slot == SLOT.SIGNATURE
            else fake_yubikey.pub_key
        )

        correct_key.verify(sig, payload, padding.PKCS1v15(), hashes.SHA256())
        with pytest.raises(InvalidSignature):
            wrong_key.verify(sig, payload, padding.PKCS1v15(), hashes.SHA256())
        signed_slots.add(slot)

    assert signed_slots == {SLOT.SIGNATURE, SLOT.AUTHENTICATION}


def test_read_and_check_single_yubikey_auto_selects_sole_occupied_slot(
    fake_yubikey,
):
    # only one slot (SIGNATURE, the fixture's default) is occupied, so there
    # is nothing to disambiguate - no prompt should be shown.
    taf_repo = _MinimalTafRepo({fake_yubikey.tuf_key.public_key.keyid: "root1"})

    result = yk._read_and_check_single_yubikey(
        role="root",
        key_name="root1",
        taf_repo=taf_repo,
        pin_manager=_pin_manager(fake_yubikey),
        registering_new_key=True,
        creating_new_key=False,
        pin_confirm=False,
        pin_repeat=False,
        prompt_message=None,
        retrying=False,
        yubikeys_to_skip=None,
        key_id_pins=None,
    )

    assert result is not None
    public_key, serial_num, key_name, slot = result
    assert slot == SLOT.SIGNATURE
    assert public_key.keyid == fake_yubikey.tuf_key.public_key.keyid
    assert serial_num == fake_yubikey.serial


def test_read_and_check_single_yubikey_returns_none_when_reusing_empty_device(
    fake_yubikey, monkeypatch
):
    # "reuse an already set up Yubikey" was chosen, but this device has no
    # key on any slot - there's nothing to reuse. Must fail clearly and
    # without ever asking for a PIN, instead of proceeding with
    # public_key=None (which crashed certificate export downstream).
    monkeypatch.setattr(yk, "get_piv_public_keys_tuf", lambda *a, **k: {})

    def _unexpected_prompt(*args, **kwargs):
        raise AssertionError("should not ask for a PIN - nothing to reuse")

    with mock.patch("click.prompt", side_effect=_unexpected_prompt), mock.patch(
        "taf.yubikey.yubikey.get_pin_for", side_effect=_unexpected_prompt
    ):
        result = yk._read_and_check_single_yubikey(
            role="root",
            key_name="root1",
            taf_repo=_MinimalTafRepo({}),
            pin_manager=PinManager(),
            registering_new_key=True,
            creating_new_key=False,
            pin_confirm=False,
            pin_repeat=False,
            prompt_message=None,
            retrying=False,
            yubikeys_to_skip=None,
            key_id_pins=None,
        )

    assert result is None


def test_read_and_check_single_yubikey_prompts_when_multiple_slots_occupied(
    fake_yubikey, keystore
):
    # more than one key is set up on this device - there's no way to know
    # which one the user means, so they must be asked to pick.
    new_key_pem = (keystore / "root2").read_bytes()
    yk.setup(
        pin="123456",
        serial=fake_yubikey.serial,
        cert_cn="Second key",
        private_key_pem=new_key_pem,
        slot=SLOT.AUTHENTICATION,
    )
    auth_key = load_signer_from_file(keystore / "root2").public_key
    taf_repo = _MinimalTafRepo(
        {
            fake_yubikey.tuf_key.public_key.keyid: "root1",
            auth_key.keyid: "root2",
        }
    )

    # AUTHENTICATION (slot value 154) sorts before SIGNATURE (156), so
    # option 1 is AUTHENTICATION - select it to prove the user's choice
    # (not SIGNATURE) is what gets used.
    with mock.patch("click.prompt", return_value=1) as prompt:
        result = yk._read_and_check_single_yubikey(
            role="root",
            key_name="root2",
            taf_repo=taf_repo,
            pin_manager=_pin_manager(fake_yubikey),
            registering_new_key=True,
            creating_new_key=False,
            pin_confirm=False,
            pin_repeat=False,
            prompt_message=None,
            retrying=False,
            yubikeys_to_skip=None,
            key_id_pins=None,
        )
    prompt.assert_called_once()

    assert result is not None
    public_key, serial_num, key_name, slot = result
    assert slot == SLOT.AUTHENTICATION
    assert public_key.keyid == auth_key.keyid


def test_prompt_for_new_key_slot_auto_selects_sole_free_slot():
    # SIGNATURE, KEY_MANAGEMENT and CARD_AUTH are occupied - AUTHENTICATION
    # is the only free slot, so there's nothing to ask about.
    occupied = {SLOT.SIGNATURE, SLOT.KEY_MANAGEMENT, SLOT.CARD_AUTH}
    with mock.patch("click.prompt") as prompt:
        slot = yk._prompt_for_new_key_slot("123456", occupied)
    prompt.assert_not_called()
    assert slot == SLOT.AUTHENTICATION


def test_prompt_for_new_key_slot_prompts_when_multiple_free_slots():
    # only SIGNATURE is occupied - AUTHENTICATION, KEY_MANAGEMENT and
    # CARD_AUTH are all free, so the user must pick one.
    occupied = {SLOT.SIGNATURE}
    # sorted by slot value: AUTHENTICATION(154), KEY_MANAGEMENT(157),
    # CARD_AUTH(158) - option 2 is KEY_MANAGEMENT
    with mock.patch("click.prompt", return_value=2) as prompt:
        slot = yk._prompt_for_new_key_slot("123456", occupied)
    prompt.assert_called_once()
    assert slot == SLOT.KEY_MANAGEMENT


def test_prompt_for_new_key_slot_raises_when_no_free_slot():
    occupied = {
        SLOT.SIGNATURE,
        SLOT.AUTHENTICATION,
        SLOT.KEY_MANAGEMENT,
        SLOT.CARD_AUTH,
    }
    with mock.patch("click.prompt") as prompt:
        with pytest.raises(YubikeyError, match="no free slot"):
            yk._prompt_for_new_key_slot("123456", occupied)
    prompt.assert_not_called()


def test_setup_yubikey_creates_new_key_in_a_free_non_signature_slot(
    fake_yubikey, monkeypatch
):
    # SIGNATURE is already occupied by the fixture's default key - creating
    # a new key must land in a different, free slot instead of failing.
    monkeypatch.setattr("builtins.input", lambda prompt="": "New signer")
    auth_repo = _MinimalTafRepo({}, pin_manager=_pin_manager(fake_yubikey))

    with mock.patch(
        "click.confirm", return_value=False
    ), mock.patch(  # "reuse already set up Yubikey?" -> no, create a new one
        "click.prompt", return_value=1
    ):
        key, serial_num, slot = taf_keys._setup_yubikey(
            auth_repo, "root", "root1", key_size=2048
        )

    assert slot == SLOT.AUTHENTICATION
    status = yk.get_slot_status(serial=fake_yubikey.serial)[fake_yubikey.serial]
    assert status[SLOT.AUTHENTICATION] is not None
    assert (
        status[SLOT.SIGNATURE].public_key().public_numbers()
        == fake_yubikey.pub_key.public_numbers()
    )


def test_setup_yubikey_updates_store_with_generated_key_for_cert_export(
    fake_yubikey, monkeypatch, tmp_path
):
    # a newly created key is recorded in yubikey_store with public_key=None
    # (it doesn't exist yet at that point) - _setup_yubikey must refresh
    # that entry once the key is actually generated, since certs_dir export
    # relies on get_roles_of_key(serial, key) finding a real public key
    # there, not crashing or silently keeping the stale None.
    monkeypatch.setattr("builtins.input", lambda prompt="": "New signer")
    auth_repo = _MinimalTafRepo({}, pin_manager=_pin_manager(fake_yubikey))

    with mock.patch(
        "click.confirm", return_value=False
    ), mock.patch(  # "reuse already set up Yubikey?" -> no, create a new one
        "click.prompt", return_value=1
    ):
        key, serial_num, slot = taf_keys._setup_yubikey(
            auth_repo, "root", "root1", key_size=2048, certs_dir=str(tmp_path)
        )

    assert auth_repo.yubikey_store.get_key_data("root1") == (key, serial_num, slot)
    assert list(tmp_path.glob(f"{key.keyid}.cert"))


def test_load_and_verify_yubikey_uses_the_slot_the_user_picked(fake_yubikey, keystore):
    new_key_pem = (keystore / "root2").read_bytes()
    yk.setup(
        pin="123456",
        serial=fake_yubikey.serial,
        cert_cn="Second key",
        private_key_pem=new_key_pem,
        slot=SLOT.AUTHENTICATION,
    )
    auth_key = load_signer_from_file(keystore / "root2").public_key
    taf_repo = _MinimalTafRepo(
        {
            fake_yubikey.tuf_key.public_key.keyid: "root1",
            auth_key.keyid: "root2",
        },
        pin_manager=_pin_manager(fake_yubikey),
    )

    # option 1 is AUTHENTICATION - the correct one for root2
    with mock.patch("click.prompt", return_value=1), mock.patch(
        "click.confirm", return_value=True
    ):
        result = taf_keys._load_and_verify_yubikey(
            "root", "root2", auth_key, taf_repo=taf_repo
        )

    assert result == (fake_yubikey.serial, SLOT.AUTHENTICATION)


def test_load_and_verify_yubikey_reports_mismatch_when_wrong_slot_picked(
    fake_yubikey, keystore
):
    # the caller already knows which key it wants (public_key) - if the
    # user picks a different slot at the prompt, that must be caught as a
    # mismatch rather than silently accepted.
    new_key_pem = (keystore / "root2").read_bytes()
    yk.setup(
        pin="123456",
        serial=fake_yubikey.serial,
        cert_cn="Second key",
        private_key_pem=new_key_pem,
        slot=SLOT.AUTHENTICATION,
    )
    auth_key = load_signer_from_file(keystore / "root2").public_key
    taf_repo = _MinimalTafRepo(
        {
            fake_yubikey.tuf_key.public_key.keyid: "root1",
            auth_key.keyid: "root2",
        },
        pin_manager=_pin_manager(fake_yubikey),
    )

    # option 2 is SIGNATURE (the fixture's default key) - the wrong one,
    # since we're looking for root2 (AUTHENTICATION). First confirm is
    # "Sign using ... Yubikey?" (yes), second is "Try again?" (no, so it
    # gives up instead of looping and re-prompting for a slot forever).
    with mock.patch("click.prompt", return_value=2), mock.patch(
        "click.confirm", side_effect=[True, False]
    ):
        result = taf_keys._load_and_verify_yubikey(
            "root", "root2", auth_key, taf_repo=taf_repo
        )

    assert result is None


class TestYubiKeyStore:
    def test_add_key_data_preserves_roles_across_multiple_calls(self):
        # a single key can be used to sign more than one role - previously
        # recorded roles for the same key_name must not be lost when it's
        # registered for another role afterwards.
        store = YubiKeyStore()
        store.add_key_data("root1", "111", "pubkey-obj", "root", slot=SLOT.SIGNATURE)
        store.add_key_data("root1", "111", "pubkey-obj", "targets", slot=SLOT.SIGNATURE)

        assert store.is_loaded_for_role("111", "root")
        assert store.is_loaded_for_role("111", "targets")

    def test_add_key_data_dedupes_role(self):
        store = YubiKeyStore()
        store.add_key_data("root1", "111", "pubkey-obj", "root")
        store.add_key_data("root1", "111", "pubkey-obj", "root")

        assert store.get_roles_of_key("111") == ["root"]

    def test_get_key_data_returns_slot(self):
        store = YubiKeyStore()
        store.add_key_data(
            "root1", "111", "pubkey-obj", "root", slot=SLOT.AUTHENTICATION
        )

        public_key, serial_num, slot = store.get_key_data("root1")
        assert public_key == "pubkey-obj"
        assert serial_num == "111"
        assert slot == SLOT.AUTHENTICATION

    def test_get_roles_of_key_isolates_keys_sharing_one_device(self):
        # two different keys (different slots) on the same physical device,
        # each used for a different role - each key's own role count must
        # not be inflated by the other key sharing its serial number.
        class _FakeKey:
            def __init__(self, keyid):
                self.keyid = keyid

        key_a = _FakeKey("keyid-a")
        key_b = _FakeKey("keyid-b")
        store = YubiKeyStore()
        store.add_key_data("root1", "111", key_a, "root", slot=SLOT.SIGNATURE)
        store.add_key_data("root2", "111", key_b, "targets", slot=SLOT.AUTHENTICATION)

        assert store.get_roles_of_key("111", public_key=key_a) == ["root"]
        assert store.get_roles_of_key("111", public_key=key_b) == ["targets"]
        assert set(store.get_roles_of_key("111")) == {"root", "targets"}
