import taf.yubikey
from taf.tests import TEST_WITH_REAL_YK
from taf.tests.conftest import KEYSTORE_PATH

from pytest import fixture
from taf.tests.yubikey_utils import TargetYubiKey, _yk_piv_ctrl_mock


def pytest_configure(config):
    if not TEST_WITH_REAL_YK:
        taf.yubikey._yk_piv_ctrl = _yk_piv_ctrl_mock


@fixture
def targets_yk(pytestconfig):
    """Targets YubiKey."""
    return TargetYubiKey(KEYSTORE_PATH, pytestconfig.option.signature_scheme)
