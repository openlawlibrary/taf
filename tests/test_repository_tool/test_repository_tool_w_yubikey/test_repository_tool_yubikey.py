import pytest

try:
    import taf.yubikey as yk
    YKMAN_AVAILABLE = yk.YKMAN_AVAILABLE
except ImportError:
    YKMAN_AVAILABLE = False

@pytest.mark.skipif(not YKMAN_AVAILABLE, reason="taf.yubikey or ykman module is not available")
def test_repository_tool_function_that_uses_yubikey():
    assert yk.some_function_using_ykman() is not None

@pytest.mark.skipif(not YKMAN_AVAILABLE, reason="taf.yubikey or ykman module is not available")
def test_another_repository_tool_function_using_yubikey():
    result = yk.some_function_using_ykman()
    assert result is not None
