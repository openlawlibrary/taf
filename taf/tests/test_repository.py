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
                assert repo.path == Path(json_data["library_dir"], json_data["name"]).resolve()
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


# def test_to_json_dict():
#     library_dir = str(Path("path").resolve())
#     name = "namespace/repo"
#     urls = ["http://github.com/namespace/repo", "http://gitlab.com/namespace/repo"]
#     custom = {"a": "b"}
#     conf_directory_root = (str(Path("path")),)
#     out_of_band_authentication = ("123456789",)
#     hosts = ({"host1": "something"},)

#     def _check_values(repo, json_data):
#         for name, value in json_data.items():
#             if name == "path":
#                 assert value == root_dir
#             else:
#                 assert getattr(repo, name) == value

#     for repo_path, repo_name in ((root_dir, name), (Path(root_dir, name), None)):
#         repo = GitRepository(
#             repo_path,
#             repo_name,
#             urls=urls,
#             custom=custom,
#         )
#         json_data = repo.to_json_dict()
#         _check_values(repo, json_data)
#         repo = AuthenticationRepository(
#             repo_path,
#             repo_name,
#             urls=urls,
#             custom=custom,
#             conf_directory_root=conf_directory_root,
#             out_of_band_authentication=out_of_band_authentication,
#             hosts=hosts,
#         )
#         _check_values(repo, json_data)
