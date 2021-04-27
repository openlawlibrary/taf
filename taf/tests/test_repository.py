import pytest

from taf.exceptions import InvalidRepositoryError
from taf.git import GitRepository


def test_name_validation_valid_names():
    names = ["namespace/repo1", "namespace1/repo1"]
    for name in names:
        repo = GitRepository("path", name)
        assert name == repo.name


def test_name_validation_invalid_names():
    names = ["repo1", "../namespace/repo1", "/namespace/repo1"]
    for name in names:
        with pytest.raises(InvalidRepositoryError):
            repo = GitRepository("path", name)


def test_url_validation_valid_urls():
    urls = [
        "https://github.com/account/repo_name.git",
        "https://github.com/account/repo_name",
        "http://github.com/account/repo_name.git",
        "http://github.com/account/repo_name",
        "git@github.com:openlawlibrary/taf.git",
        "git@github.com:openlawlibrary/taf",
    ]
    repo = GitRepository("path", urls=urls)
    for test_url, repo_url in zip(urls, repo.urls):
        assert test_url == repo_url


def test_url_invalid_urls():
    urls = ["abc://something.com"]
    with pytest.raises(InvalidRepositoryError):
        GitRepository("path", urls=urls)
