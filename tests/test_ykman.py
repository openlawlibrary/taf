import pytest
try:
    from ykman.device import list_all_devices
    YKMAN_AVAILABLE = True
except ImportError:
    YKMAN_AVAILABLE = False

@pytest.mark.skipif(not YKMAN_AVAILABLE, reason="ykman module is not available")
def test_some_function_that_uses_ykman():
    pass
pytest