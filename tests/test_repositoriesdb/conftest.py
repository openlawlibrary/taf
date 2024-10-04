from contextlib import contextmanager
from taf.tests.conftest import origin_repos_group

import taf.repositoriesdb as repositoriesdb
from pytest import fixture


@fixture(scope="session", autouse=True)
def repositoriesdb_test_repositories():
    test_dir = "test-repositoriesdb"
    with origin_repos_group(test_dir) as origins:
        yield origins


@contextmanager
def load_repositories(auth_repo, **kwargs):
    repositoriesdb.load_repositories(auth_repo, **kwargs)
    yield
    repositoriesdb.clear_repositories_db()
