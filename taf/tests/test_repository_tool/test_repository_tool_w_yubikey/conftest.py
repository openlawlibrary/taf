import pytest

try:
    import taf.yubikey as yk
    from taf.tools.yubikey.yubikey_utils import (
        export_yk_certificate,
        export_yk_public_pem,
        get_yk_roles,
        setup_signing_yubikey,
        setup_test_yubikey
    )
    YKMAN_AVAILABLE = True
except ImportError:
    YKMAN_AVAILABLE = False

@pytest.fixture
def targets_yk(pytestconfig):
    """Targets YubiKey."""
    if YKMAN_AVAILABLE:
        return setup_test_yubikey(pytestconfig.option.signature_scheme)
    else:
        pytest.skip("YubiKey-related functionality not available (ykman not installed).")
