import os
from types import SimpleNamespace

import pytest

from taf.exceptions import InvalidPINError
from taf.yubikey.yubikey import _pin_from_keys_mapping, _resolve_and_cache_pin
from taf.yubikey.yubikey_manager import PinManager


class DummyKey(SimpleNamespace):
    """Just enough shape for .keyval['public']"""

    def __init__(self, pem: str):
        super().__init__(keyval={"public": pem})


@pytest.fixture(autouse=True)
def clean_env():
    """Each test gets a fresh copy of os.environ."""
    snapshot = os.environ.copy()
    yield
    os.environ.clear()
    os.environ.update(snapshot)


def test_pin_found():
    pem = "-----BEGIN PUBLIC KEY-----\nABC\n-----END PUBLIC KEY-----"
    os.environ["PIN_MY_KEY"] = "123456"

    mapping = {
        "my-key": {
            "public": pem,
            "keyid": "x",
            "scheme": "rsa",
        }
    }
    key = DummyKey(pem)

    assert _pin_from_keys_mapping(key, mapping) == "123456"


def test_resolve_and_cache_pin_when_pin_from_environment_is_wrong(fake_yubikey):
    os.environ[f"PIN_{fake_yubikey.serial}"] = "000000"
    pin_manager = PinManager()

    with pytest.raises(
        InvalidPINError, match="from the environment is incorrect, 2 retries left"
    ):
        _resolve_and_cache_pin(
            pin_manager, fake_yubikey.serial, None, None, "root1", False, False, None
        )
    assert pin_manager.get_pin(fake_yubikey.serial) is None


def test_pin_not_found():
    pem = "PEM"
    key = DummyKey(pem)

    assert _pin_from_keys_mapping(key, {}) is None

    mapping = {"my-key": {"public": pem, "keyid": "x", "scheme": "rsa"}}
    assert _pin_from_keys_mapping(key, mapping) is None
