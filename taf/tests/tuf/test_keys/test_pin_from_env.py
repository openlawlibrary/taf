import os

import pytest

from taf.constants import DEFAULT_RSA_SIGNATURE_SCHEME
from taf.exceptions import InvalidPINError
from taf.tuf.keys import get_sslib_key_from_value
from taf.yubikey.yubikey import _pin_from_keys_mapping, _resolve_and_cache_pin
from taf.yubikey.yubikey_manager import PinManager


@pytest.fixture(autouse=True)
def clean_env():
    """Each test gets a fresh copy of os.environ."""
    snapshot = os.environ.copy()
    yield
    os.environ.clear()
    os.environ.update(snapshot)


def test_pin_found(keystore):
    key = get_sslib_key_from_value(
        (keystore / "root1.pub").read_text(), DEFAULT_RSA_SIGNATURE_SCHEME
    )
    os.environ["PIN_MY_KEY"] = "123456"

    mapping = {
        "my-key": {
            "public": key.keyval["public"],
            "keyid": "x",
            "scheme": "rsa",
        }
    }

    assert _pin_from_keys_mapping(key, mapping) == "123456"


def test_resolve_and_cache_pin_when_pin_from_environment_is_wrong(fake_yubikey):
    os.environ[f"PIN_{fake_yubikey.serial}"] = "000000"
    pin_manager = PinManager()

    with pytest.raises(
        InvalidPINError, match="from the environment is incorrect, 2 retries left"
    ):
        _resolve_and_cache_pin(
            pin_manager,
            fake_yubikey.serial,
            public_key=None,
            taf_dir=None,
            key_name="root1",
            pin_confirm=False,
            pin_repeat=False,
            key_id_pins=None,
        )
    assert pin_manager.get_pin(fake_yubikey.serial) is None


def test_pin_not_found(keystore):
    key = get_sslib_key_from_value(
        (keystore / "root2.pub").read_text(), DEFAULT_RSA_SIGNATURE_SCHEME
    )

    assert _pin_from_keys_mapping(key, {}) is None

    mapping = {
        "my-key": {"public": key.keyval["public"], "keyid": "x", "scheme": "rsa"}
    }
    assert _pin_from_keys_mapping(key, mapping) is None
