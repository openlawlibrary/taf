from collections import defaultdict
import contextlib
from typing import Dict, List, Optional, Tuple
from taf.tuf.keys import SSlibKey


class YubiKeyStore:
    def __init__(self):
        # Initializes the dictionary to store YubiKey data
        self._yubikeys_data = defaultdict(dict)

    @property
    def yubikeys_data(self) -> Dict:
        return self._yubikeys_data

    def is_loaded(self, serial_number) -> bool:
        return any(
            data["serial"] == serial_number for data in self._yubikeys_data.values()
        )

    def is_loaded_for_role(self, serial_number: str, role_name: str) -> bool:
        for data in self._yubikeys_data.values():
            if data["serial"] == serial_number and role_name in data["roles"]:
                return True
        return False

    def is_key_name_loaded(self, key_name: str) -> bool:
        """Check if the key name is already loaded."""
        return key_name in self._yubikeys_data

    def add_key_data(
        self,
        key_name: str,
        serial_num: str,
        public_key: SSlibKey,
        role_name: str,
    ) -> None:
        """Add data associated with a YubiKey."""
        if role_name in self._yubikeys_data:
            key_data = self._yubikeys_data[key_name]
        else:
            key_data = {"serial": serial_num, "public_key": public_key, "roles": []}
        key_data["roles"].append(role_name)
        self._yubikeys_data[key_name] = key_data

    def get_key_data(self, key_name: str) -> Optional[Tuple[str, SSlibKey]]:
        """Retrieve data associated with a given YubiKey name."""
        if not self.is_key_name_loaded(key_name):
            return None
        key_data = self._yubikeys_data.get(key_name)
        return key_data["public_key"], key_data["serial"]

    def get_roles_of_key(self, serial_number: str) -> List[str]:
        roles = []
        for data in self._yubikeys_data.values():
            if data["serial"] == serial_number:
                roles.extend(data["roles"])
        return roles

    def remove_key_data(self, key_name: str) -> bool:
        """Remove data associated with a given YubiKey name if it exists."""
        if self.is_key_name_loaded(key_name):
            del self._yubikeys_data[key_name]
            return True
        return False


class PinManager:
    """
    Manages PIN storage and retrieval for YubiKeys, providing a centralized mechanism
    to handle adding and retrieving PINs to and from storage.

    Attributes:
        auto_continue (bool): If set to True, suppresses prompts when they are not necessary, allowing
                              uninterrupted execution. Default is False.
        _pins (dict): A private dictionary that stores PINs, keyed by an identifier (e.g., the YubiKey serial number).
    """

    def __init__(self, auto_continue=False):
        self._pins = {}
        # Automatically continue without prompts e.g. when attempting to load more keys
        self.auto_continue = auto_continue

    def add_pin(self, serial_number, pin):
        self._pins[serial_number] = pin

    def clear_pins(self):
        for key in list(self._pins.keys()):
            self._pins[key] = None
        self._pins.clear()

    def get_pin(self, serial_number):
        return self._pins.get(serial_number)


@contextlib.contextmanager
def manage_pins():
    """
    Context manager to handle the lifecycle of PinManager instances.

    Yields:
        PinManager: An instance of PinManager, ready for use.

    Ensures that PINs are cleared from memory immediately after the operations
    involving the PinManager are completed, maintaining security.
    """
    pin_manager = PinManager()
    try:
        yield pin_manager
    finally:
        pin_manager.clear_pins()


def pin_managed(func):
    """
    Decorator that wraps a function to automatically provide it with a managed PinManager instance.

    Args:
        func (Callable): The function to be decorated, which will use a PinManager.

    Returns:
        Callable: The wrapped function with a PinManager instance passed as a keyword argument.

    This decorator abstracts away the creation and cleanup of PinManager instances, allowing
    functions to utilize a PinManager without concern for its lifecycle.
    """

    def wrapper(*args, **kwargs):
        with manage_pins() as pin_manager:
            kwargs["pin_manager"] = pin_manager
            return func(*args, **kwargs)

    return wrapper
