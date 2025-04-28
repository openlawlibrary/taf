import os
from types import SimpleNamespace

import pytest

from taf.yubikey.yubikey import _pin_from_keys_mapping


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
    os.environ["MY_KEY_PIN"] = "123456"

    mapping = {
        "my-key": {
            "public": pem,
            "keyid": "x",
            "scheme": "rsa",
        }
    }
    key = DummyKey(pem)

    assert _pin_from_keys_mapping(key, mapping) == "123456"


def test_pin_not_found():
    pem = "PEM"
    key = DummyKey(pem)

    assert _pin_from_keys_mapping(key, {}) is None

    mapping = {"my-key": {"public": pem, "keyid": "x", "scheme": "rsa"}}
    assert _pin_from_keys_mapping(key, mapping) is None
