from pathlib import Path
import shutil
import uuid
from taf.api.dependencies import add_dependency
from taf.messages import git_commit_message
import taf.repositoriesdb as repositoriesdb
from taf.auth_repo import AuthenticationRepository
from taf.git import GitRepository
from pytest import fixture
from taf.api.repository import create_repository
from taf.api.targets import (
    add_target_repo,
    register_target_files,
    remove_target_repo,
    update_target_repos_from_repositories_json,
)
from taf.tests.conftest import CLIENT_DIR_PATH
from taf.tests.test_api.util import (
    check_if_targets_signed,
    copy_mirrors_json,
    copy_repositories_json,
    check_target_file,
)
from taf.utils import on_rm_error
from tuf.repository_tool import TARGETS_DIRECTORY_NAME


AUTH_REPO_NAME = "auth"


def _init_auth_repo_dir():
    random_name = str(uuid.uuid4())
    root_dir = CLIENT_DIR_PATH / random_name
    auth_path = root_dir / AUTH_REPO_NAME
    auth_path.mkdir(exist_ok=True, parents=True)
    return auth_path


@fixture(scope="module")
def child_repo1_path():
    repo_path = _init_auth_repo_dir()
    yield repo_path


@fixture(scope="module")
def child_repo2_path():
    repo_path = _init_auth_repo_dir()
    yield repo_path


@fixture(scope="module")
def parent_repo_path():
    repo_path = _init_auth_repo_dir()
    yield repo_path
    shutil.rmtree(str(repo_path.parent), onerror=on_rm_error)


def test_setup_repositories(
    child_repo1_path,
    child_repo2_path,
    parent_repo_path,
    no_yubikeys_path,
    api_keystore,
):
    for path in (child_repo1_path, child_repo2_path, parent_repo_path):
        create_repository(
            str(path),
            roles_key_infos=no_yubikeys_path,
            keystore=api_keystore,
            commit=True,
        )


def test_add_dependency_when_on_filesystem(
    parent_repo_path, child_repo1_path, child_repo2_path, api_keystore
):
    auth_repo = AuthenticationRepository(path=parent_repo_path)
    initial_commits_num = len(auth_repo.list_commits())
    child_repository1 = AuthenticationRepository(path=child_repo1_path)
    child_repository2 = AuthenticationRepository(path=child_repo2_path)

    add_dependency(
        path=str(parent_repo_path),
        dependency_name=child_repository1.name,
        keystore=api_keystore,
        branch_name=None,
        out_of_band_commit=None,
        no_prompt=True,
        push=False,
    )
    commits = auth_repo.list_commits()
    assert len(commits) == initial_commits_num + 1
    assert commits[0].message.strip() == git_commit_message(
        "add-dependency", dependency_name=child_repository1.name
    )
    # TODO check dependencies.json
