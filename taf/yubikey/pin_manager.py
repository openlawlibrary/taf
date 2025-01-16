import contextlib


class PinManager():

    def __init__(self):
        self._pins = {}

    def set_pin(self, serial_number, pin):
        self._pins[serial_number] = pin

    def get_pin(self, serial_number):
        return self._pins.get(serial_number)

    def clear_pins(self):
        for key in list(self._pins.keys()):
            self._pins[key] = None
        self._pins.clear()



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
