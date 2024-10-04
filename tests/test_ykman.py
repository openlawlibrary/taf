import pytest

try:
    import taf.yubikey as yk
    YKMAN_AVAILABLE = yk.YKMAN_AVAILABLE  
except ImportError:
    YKMAN_AVAILABLE = False

# existing tests that require taf.yubikey to be skipped if ykman is not available
@pytest.mark.skipif(not YKMAN_AVAILABLE, reason="taf.yubikey or ykman module is not available")
def test_repository_tool_function_that_uses_yubikey():
    assert yk.some_function_using_ykman() is not None

# apply the same skip condition for the other existing tests that rely on taf.yubikey
@pytest.mark.skipif(not YKMAN_AVAILABLE, reason="taf.yubikey or ykman module is not available")
def test_another_function_using_yubikey():
    result = yk.some_function_using_ykman()
    assert result is not None
pytest