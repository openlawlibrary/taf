from pathlib import Path
from unittest import mock

import pytest
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from yubikit.core import NotSupportedError
from yubikit.piv import DEFAULT_MANAGEMENT_KEY, SLOT

import taf.api.yubikey as yk_api
import taf.keys as taf_keys
import taf.yubikey.yubikey as yk
from taf.exceptions import YubikeyError
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

    def __init__(self, key_names_by_keyid: dict, pin_manager: PinManager = None):
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
