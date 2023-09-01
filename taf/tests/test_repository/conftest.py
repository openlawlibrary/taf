from taf.tests.conftest import origin_repos_group

from pytest import fixture


@fixture(scope="session", autouse=True)
def repository_test_repositories():
    test_dir = "test-repository"
    with origin_repos_group(test_dir) as origins:
        yield origins
