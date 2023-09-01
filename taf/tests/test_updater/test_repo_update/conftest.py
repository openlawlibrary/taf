from taf.tests.conftest import origin_repos_group
from tuf.ngclient._internal import trusted_metadata_set
import taf.yubikey
from pytest import fixture
from taf.tests import TEST_WITH_REAL_YK
from taf.tests.yubikey_utils import (
    _yk_piv_ctrl_mock,
)


original_tuf_trusted_metadata_set = trusted_metadata_set.TrustedMetadataSet


def pytest_configure(config):
    if not TEST_WITH_REAL_YK:
        taf.yubikey._yk_piv_ctrl = _yk_piv_ctrl_mock


@fixture(scope="session", autouse=True)
def updater_repositories():
    test_dir = "test-updater"
    with origin_repos_group(test_dir) as origins:
        yield origins
