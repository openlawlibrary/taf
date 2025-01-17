from collections import defaultdict
import contextlib
from typing import Any, Dict, Optional, Tuple
from taf.tuf.keys import SSlibKey


class YubiKeyStore:
    def __init__(self):
        # Initializes the dictionary to store YubiKey data
        self._yubikeys_data = defaultdict(dict)

    def is_key_name_loaded(self, key_name: str) -> bool:
        """Check if the key name is already loaded."""
        return key_name in self._yubikeys_data

    def add_key_data(self, key_name: str, serial_num: str, public_key: SSlibKey) -> None:
        """Add data associated with a YubiKey."""
        if not self.is_key_name_loaded(key_name):
            self._yubikeys_data[key_name] = {
                "serial": serial_num,
                "public_key": public_key
            }

    def get_key_data(self, key_name: str) -> Tuple[str, SSlibKey]:
        """Retrieve data associated with a given YubiKey name."""
        key_data = self._yubikeys_data.get(key_name)
        return key_data["public_key"], key_data["serial"]

    def remove_key_data(self, key_name: str) -> bool:
        """Remove data associated with a given YubiKey name if it exists."""
        if self.is_key_name_loaded(key_name):
            del self._yubikeys_data[key_name]
            return True
        return False


class PinManager():

    def __init__(self):
        self._pins = {}

    def add_pin(self, serial_number, pin):
        self._pins[serial_number] = pin

    def clear_pins(self):
        for key in list(self._pins.keys()):
            self._pins[key] = None
        self._pins.clear()

    def get_pin(self, serial_number):
        return self._pins.get(serial_number)

    def is_loaded(self, serial_number):
        return self.get_pin(serial_number) is not None


@contextlib.contextmanager
def manage_pins():
    pin_manager = PinManager()
    try:
        yield pin_manager
    finally:
        pin_manager.clear_pins()


def pin_managed(func):
    def wrapper(*args, **kwargs):
        with manage_pins() as pin_manager:
            kwargs['pin_manager'] = pin_manager
            return func(*args, **kwargs)
    return wrapper
