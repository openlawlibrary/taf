import pytest
from pathlib import Path

from taf.exceptions import InvalidRepositoryError
from taf.git import GitRepository
from taf.auth_repo import AuthenticationRepository


def test_name_validation_valid_names():
    names = ["namespace/repo1", "namespace1/repo1"]
    for name in names:
        repo = GitRepository(path=Path("path", name))
        assert name == repo.name
        repo = GitRepository("path", name)
        assert name == repo.name


def test_name_validation_invalid_names():
    names = ["repo1", "../namespace/repo1", "/namespace/repo1"]
    for name in names:
        with pytest.raises(InvalidRepositoryError):
            GitRepository("path", name)


def test_path_validation_valid_path():
    paths = ["/test1/test2/test3", "../test1/test2/test3"]
    name = "namespace/repo1"
    for path in paths:
        repo = GitRepository(path, name)
        assert name == repo.name
        assert Path(path, name).resolve() == repo.path
        repo = GitRepository(path=Path(path, name))
        assert name == repo.name
        assert Path(path, name).resolve() == repo.path


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
    repo = GitRepository("path", "namespace/repo", urls=urls)
    for test_url, repo_url in zip(urls, repo.urls):
        assert test_url == repo_url


def test_url_invalid_urls():
    urls = ["abc://something.com"]
    with pytest.raises(InvalidRepositoryError):
        GitRepository("path", "namespace/repo", urls=urls)


def test_from_json_dict():
    data = {
        "library_dir": "path",
        "name": "namespace/repo",
        "urls": [
            "http://github.com/namespace/repo",
            "http://gitlab.com/namespace/repo",
        ],
        "default_branch": "master",
        "custom": {"a": "b"},
    }

    def _check_values(repo, json_data):
        for attr_name, attr_value in json_data.items():
            if attr_name == "library_dir":
                attr_value = Path(json_data["library_dir"]).resolve()
                assert (
                    repo.path
                    == Path(json_data["library_dir"], json_data["name"]).resolve()
                )
            elif attr_name in ("path", "conf_directory_root"):
                attr_value = Path(json_data[attr_name]).resolve()
            assert getattr(repo, attr_name) == attr_value

    repo = GitRepository.from_json_dict(data)
    _check_values(repo, data)

    auth_data = data.copy()
    auth_data.update(
        {
            "conf_directory_root": "path",
            "out_of_band_authentication": "123456789",
            "hosts": {"host1": "something"},
        }
    )
    auth_repo = AuthenticationRepository.from_json_dict(auth_data)
    _check_values(auth_repo, auth_data)

    for json_data in (data, auth_data):
        json_data["path"] = Path(json_data["library_dir"], json_data["name"])
        json_data.pop("library_dir")
        json_data.pop("name")

    repo = GitRepository.from_json_dict(data)
    _check_values(repo, data)
    auth_repo = AuthenticationRepository.from_json_dict(auth_data)
    _check_values(auth_repo, auth_data)


def test_to_json_dict():
    library_dir = Path("path").resolve()
    name = "namespace/repo"
    urls = ["http://github.com/namespace/repo", "http://gitlab.com/namespace/repo"]
    custom = {"a": "b"}
    conf_directory_root = Path("path").resolve()
    out_of_band_authentication = ("123456789",)
    hosts = ({"host1": "something"},)

    def _check_values(repo, json_data):
        for attr_name, attr_value in json_data.items():
            repo_value = getattr(repo, attr_name)
            if isinstance(repo_value, Path):
                assert str(repo_value) == attr_value
            else:
                assert repo_value == attr_value

    for repo_library_dir, repo_name, repo_path, in (
        (library_dir, name, None),
        (None, None, Path(library_dir, name)),
    ):
        repo = GitRepository(
            library_dir, name, urls=urls, custom=custom, path=repo_path
        )
        json_data = repo.to_json_dict()
        _check_values(repo, json_data)
        repo = AuthenticationRepository(
            library_dir,
            name,
            urls=urls,
            custom=custom,
            conf_directory_root=conf_directory_root,
            out_of_band_authentication=out_of_band_authentication,
            hosts=hosts,
            path=repo_path,
        )
        _check_values(repo, json_data)


def test_to_from_json_roundtrip():
    library_dir_data = {
        "library_dir": Path("path").resolve(),
        "name": "namespace/repo",
        "urls": [
            "http://github.com/namespace/repo",
            "http://gitlab.com/namespace/repo",
        ],
        "default_branch": "master",
        "custom": {"a": "b"},
    }
    library_dir_auth_data = library_dir_data.copy()
    library_dir_auth_data.update(
        {
            "conf_directory_root": Path("path").resolve(),
            "out_of_band_authentication": "123456789",
            "hosts": {"host1": "something"},
        }
    )
    path_data = library_dir_data.copy()
    path_auth_data = library_dir_auth_data.copy()
    for json_data in (path_data, path_auth_data):
        json_data["path"] = Path(json_data["library_dir"], json_data["name"])
        json_data.pop("library_dir")
        json_data.pop("name")

    def _check_values(input_data, output_data):
        for key, value in input_data.items():
            if key == "path":
                assert key not in output_data
                continue
            if isinstance(value, Path):
                assert str(value) == output_data[key]
            else:
                assert value == output_data[key]

    for data, auth_data in (
        (library_dir_data, library_dir_auth_data),
        (path_data, path_auth_data),
    ):
        repo = GitRepository.from_json_dict(data)
        output_data = repo.to_json_dict()
        _check_values(data, output_data)
        auth_repo = AuthenticationRepository.from_json_dict(auth_data)
        output_data = auth_repo.to_json_dict()
        _check_values(auth_data, output_data)
