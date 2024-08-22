import shutil
import uuid
import pytest
from pathlib import Path
from taf.api.dependencies import add_dependency, remove_dependency
from taf.exceptions import TAFError
from taf.messages import git_commit_message
import taf.repositoriesdb as repositoriesdb
from taf.auth_repo import AuthenticationRepository
from pytest import fixture
from taf.api.repository import create_repository
from taf.tests.conftest import CLIENT_DIR_PATH
from taf.utils import on_rm_error


AUTH_REPO_NAME = "auth"
DEPENDENCY_NAME = "dependency/auth"


def _init_auth_repo_dir():
    random_name = str(uuid.uuid4())
    root_dir = CLIENT_DIR_PATH / random_name
    auth_path = root_dir / AUTH_REPO_NAME
    auth_path.mkdir(exist_ok=True, parents=True)
    return auth_path


@fixture(scope="module")
def child_repo_path():
    repo_path = _init_auth_repo_dir()
    yield repo_path
    shutil.rmtree(str(repo_path.parent), onerror=on_rm_error)


@fixture(scope="module")
def parent_repo_path():
    repo_path = _init_auth_repo_dir()
    yield repo_path
    shutil.rmtree(str(repo_path.parent), onerror=on_rm_error)


def test_setup_repositories(
    child_repo_path: Path,
    parent_repo_path: Path,
    no_yubikeys_path: str,
    api_keystore: str,
):
    for path in (child_repo_path, parent_repo_path):
        create_repository(
            str(path),
            roles_key_infos=no_yubikeys_path,
            keystore=api_keystore,
            commit=True,
        )


def test_add_dependency_when_on_filesystem_invalid_commit(
    parent_repo_path, child_repo_path, api_keystore
):
    auth_repo = AuthenticationRepository(path=parent_repo_path)
    initial_commits_num = len(auth_repo.list_commits())
    child_repository = AuthenticationRepository(path=child_repo_path)

    with pytest.raises(TAFError):
        add_dependency(
            path=str(parent_repo_path),
            dependency_name=child_repository.name,
            keystore=api_keystore,
            branch_name="main",
            out_of_band_commit="66d7f48e972f9fa25196523f469227dfcd85c994",
            no_prompt=True,
            push=False,
        )
    commits = auth_repo.list_commits()
    assert len(commits) == initial_commits_num


def test_add_dependency_when_on_filesystem(
    parent_repo_path, child_repo_path, api_keystore
):
    auth_repo = AuthenticationRepository(path=parent_repo_path)
    initial_commits_num = len(auth_repo.list_commits())
    child_repository = AuthenticationRepository(path=child_repo_path)

    add_dependency(
        path=str(parent_repo_path),
        dependency_name=child_repository.name,
        keystore=api_keystore,
        branch_name=None,
        out_of_band_commit=None,
        no_prompt=True,
        push=False,
    )
    commits = auth_repo.list_commits()
    assert len(commits) == initial_commits_num + 1
    assert commits[0].message.strip() == git_commit_message(
        "add-dependency", dependency_name=child_repository.name
    )

    dependencies_json = repositoriesdb.load_dependencies_json(auth_repo)
    dependencies = dependencies_json["dependencies"]
    assert child_repository.name in dependencies
    assert dependencies[child_repository.name] == {
        "out-of-band-authentication": child_repository.head_commit_sha(),
        "branch": child_repository.default_branch,
    }


def test_add_dependency_when_not_on_filesystem(parent_repo_path, api_keystore):
    auth_repo = AuthenticationRepository(path=parent_repo_path)
    initial_commits_num = len(auth_repo.list_commits())
    branch_name = "main"
    out_of_band_commit = "66d7f48e972f9fa25196523f469227dfcd85c994"
    add_dependency(
        path=str(parent_repo_path),
        dependency_name=DEPENDENCY_NAME,
        keystore=api_keystore,
        branch_name=branch_name,
        out_of_band_commit=out_of_band_commit,
        no_prompt=True,
        push=False,
    )
    commits = auth_repo.list_commits()
    assert len(commits) == initial_commits_num + 1
    assert commits[0].message.strip() == git_commit_message(
        "add-dependency", dependency_name=DEPENDENCY_NAME
    )

    dependencies_json = repositoriesdb.load_dependencies_json(auth_repo)
    dependencies = dependencies_json["dependencies"]
    assert DEPENDENCY_NAME in dependencies
    assert dependencies[DEPENDENCY_NAME] == {
        "out-of-band-authentication": out_of_band_commit,
        "branch": branch_name,
    }


def test_remove_dependency(parent_repo_path, child_repo_path, api_keystore):
    auth_repo = AuthenticationRepository(path=parent_repo_path)
    initial_commits_num = len(auth_repo.list_commits())
    child_repository = AuthenticationRepository(path=child_repo_path)

    remove_dependency(
        path=str(parent_repo_path),
        dependency_name=child_repository.name,
        keystore=api_keystore,
        push=False,
    )
    commits = auth_repo.list_commits()
    assert len(commits) == initial_commits_num + 1
    assert commits[0].message.strip() == git_commit_message(
        "remove-dependency", dependency_name=child_repository.name
    )
    dependencies_json = repositoriesdb.load_dependencies_json(auth_repo)
    dependencies = dependencies_json["dependencies"]
    assert child_repository.name not in dependencies
