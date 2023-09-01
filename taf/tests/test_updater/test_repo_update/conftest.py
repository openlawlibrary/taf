from taf.tests.conftest import origin_repos_group
from tuf.ngclient._internal import trusted_metadata_set
from pytest import fixture

original_tuf_trusted_metadata_set = trusted_metadata_set.TrustedMetadataSet


@fixture(scope="session", autouse=True)
def updater_repositories():
    test_dir = "test-updater"
    with origin_repos_group(test_dir) as origins:
        yield origins
