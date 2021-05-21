import pytest
from pathlib import Path

from taf.exceptions import InvalidRepositoryError
from taf.git import GitRepository
from taf.auth_repo import AuthenticationRepository


def test_name_validation_valid_names():
    names = ["namespace/repo1", "namespace1/repo1"]
    for name in names:
        repo = GitRepository(Path("path", name), name)
        assert name == repo.name
        repo = GitRepository(Path("path", name))
        assert name == repo.name


def test_name_validation_invalid_names():
    names = ["repo1", "../namespace/repo1", "/namespace/repo1"]
    for name in names:
        with pytest.raises(InvalidRepositoryError):
            GitRepository(Path("path", name), name)


def test_path_validation_valid_path():
    paths = ["/test1/test2/test3", "../test1/test2/test3"]
    name = "namespace/repo1"
    for path in paths:
        repo = GitRepository(path, name)
        assert name == repo.name
        assert str(Path(path, name).resolve()) == repo.path
        repo = GitRepository(Path(path, name))
        assert name == repo.name
        assert str(Path(path, name).resolve()) == repo.path


def test_path_validation_invalid_path():
    path = "/test1/test2/../test3"
    names = ["namespace/repo1", "namespace1/repo1"]
    for name in names:
        with pytest.raises(InvalidRepositoryError):
            repo = GitRepository(path, name)
            assert name == repo.name


def test_url_validation_valid_urls():
    urls = [
        "https://github.com/account/repo_name.git",
        "https://github.com/account/repo_name",
        "http://github.com/account/repo_name.git",
        "http://github.com/account/repo_name",
        "git@github.com:openlawlibrary/taf.git",
        "git@github.com:openlawlibrary/taf",
    ]
    repo = GitRepository(Path("path", "namespace", "repo"), urls=urls)
    for test_url, repo_url in zip(urls, repo.urls):
        assert test_url == repo_url


def test_url_invalid_urls():
    urls = ["abc://something.com"]
    with pytest.raises(InvalidRepositoryError):
        GitRepository("path", urls=urls)


def test_from_json_dict():
    data = {
        "path": str(Path("path", "namespace", "repo")),
        "urls": [
            "http://github.com/namespace/repo",
            "http://gitlab.com/namespace/repo",
        ],
        "name": "namespace/repo",
        "default_branch": "master",
        "custom": {"a": "b"},
    }
    repo = GitRepository.from_json_dict(data)
    data["path"] = str(Path(data["path"]).resolve())
    for attr_name, attr_value in data.items():
        assert getattr(repo, attr_name) == attr_value
    data.update(
        {
            "conf_directory_root": str(Path("path")),
            "out_of_band_authentication": "123456789",
            "hosts": {"host1": "something"},
        }
    )
    auth_repo = AuthenticationRepository.from_json_dict(data)
    for attr_name, attr_value in data.items():
        assert getattr(auth_repo, attr_name) == attr_value


def test_to_json_dict():
    repo = GitRepository(
        str(Path("path", "namespace", "repo")),
        urls=["http://github.com/namespace/repo", "http://gitlab.com/namespace/repo"],
        custom={"a": "b"},
    )
    json_data = repo.to_json_dict()
    for name, value in json_data.items():
        assert getattr(repo, name) == value

    auth_repo = AuthenticationRepository(
        str(Path("path", "namespace", "repo")),
        urls=["http://github.com/namespace/repo", "http://gitlab.com/namespace/repo"],
        custom={"a": "b"},
        conf_directory_root=str(Path("path")),
        out_of_band_authentication="123456789",
        hosts={"host1": "something"},
    )

    json_data = auth_repo.to_json_dict()
    for name, value in json_data.items():
        assert getattr(auth_repo, name) == value
