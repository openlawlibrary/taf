from pathlib import Path
import shutil
from typing import Dict
import uuid
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


@fixture(scope="module")
def library():
    random_name = str(uuid.uuid4())
    root_dir = CLIENT_DIR_PATH / random_name
    # create an initialize some target repositories
    # their content is not important
    auth_path = root_dir / AUTH_REPO_NAME
    auth_path.mkdir(exist_ok=True, parents=True)
    targets = ("target1", "target2", "target3", "new_target")
    for target in targets:
        target_repo_path = root_dir / target
        target_repo_path.mkdir()
        target_repo = GitRepository(path=target_repo_path)
        target_repo.init_repo()
        target_repo.commit_empty("Initial commit")
    yield root_dir
    shutil.rmtree(root_dir, onerror=on_rm_error)


def test_setup_auth_repo_when_add_repositories_json(
    library: Path,
    with_delegations_no_yubikeys_path: str,
    api_keystore: str,
    repositories_json_template: Dict,
    mirrors_json_path: Path,
):
    repo_path = library / "auth"
    namespace = library.name
    copy_repositories_json(repositories_json_template, namespace, repo_path)
    copy_mirrors_json(mirrors_json_path, repo_path)

    create_repository(
        str(repo_path),
        roles_key_infos=with_delegations_no_yubikeys_path,
        keystore=api_keystore,
        commit=True,
    )


def test_register_targets_when_file_added(library: Path, api_keystore: str):
    repo_path = library / "auth"
    auth_repo = AuthenticationRepository(path=repo_path)
    initial_commits_num = len(auth_repo.list_commits())
    FILENAME = "test.txt"
    # add a new file to the targets directory, check if it was signed
    file_path = repo_path / TARGETS_DIRECTORY_NAME / FILENAME
    file_path.write_text("test")
    register_target_files(repo_path, api_keystore, write=True, push=False)
    check_if_targets_signed(auth_repo, "targets", FILENAME)
    commits = auth_repo.list_commits()
    assert len(commits) == initial_commits_num + 1
    assert commits[0].message.strip() == git_commit_message("update-targets")


def test_register_targets_when_file_removed(library: Path, api_keystore: str):
    repo_path = library / "auth"
    auth_repo = AuthenticationRepository(path=repo_path)
    initial_commits_num = len(auth_repo.list_commits())
    FILENAME = "test.txt"
    # add a new file to the targets directory, check if it was signed
    file_path = repo_path / TARGETS_DIRECTORY_NAME / FILENAME
    file_path.unlink()
    register_target_files(repo_path, api_keystore, write=True, push=False)
    signed_target_files = auth_repo.get_signed_target_files()
    assert FILENAME not in signed_target_files
    commits = auth_repo.list_commits()
    assert len(commits) == initial_commits_num + 1
    assert commits[0].message.strip() == git_commit_message("update-targets")


def test_update_target_repos_from_repositories_json(library: Path, api_keystore: str):
    repo_path = library / "auth"
    auth_repo = AuthenticationRepository(path=repo_path)
    initial_commits_num = len(auth_repo.list_commits())
    namespace = library.name
    update_target_repos_from_repositories_json(
        str(repo_path),
        str(library.parent),
        api_keystore,
        push=False,
    )
    # this should create target files and save commit and branch to them, then sign
    for name in ("target1", "target2", "target3"):
        target_repo_name = f"{namespace}/{name}"
        target_repo_path = library.parent / target_repo_name
        assert check_target_file(target_repo_path, target_repo_name, auth_repo)
    commits = auth_repo.list_commits()
    assert len(commits) == initial_commits_num + 1
    assert commits[0].message.strip() == git_commit_message("update-targets")


def test_add_target_repository_when_not_on_filesystem(library: Path, api_keystore: str):
    repo_path = str(library / "auth")
    auth_repo = AuthenticationRepository(path=repo_path)
    initial_commits_num = len(auth_repo.list_commits())
    namespace = library.name
    target_repo_name = f"{namespace}/target4"
    add_target_repo(
        str(repo_path),
        None,
        target_repo_name,
        "delegated_role",
        None,
        api_keystore,
        push=False,
    )
    # verify repositories.json was updated and that changes were committed
    # then validate the repository
    repositories_json = repositoriesdb.load_repositories_json(auth_repo)
    assert repositories_json is not None
    repositories = repositories_json["repositories"]
    assert target_repo_name in repositories
    commits = auth_repo.list_commits()
    assert len(commits) == initial_commits_num + 1
    assert commits[0].message.strip() == git_commit_message(
        "add-target", target_name=target_repo_name
    )
    delegated_paths = auth_repo.get_delegated_role_property("paths", "delegated_role")
    assert target_repo_name in delegated_paths


def test_add_target_repository_when_on_filesystem(library: Path, api_keystore: str):
    repo_path = str(library / "auth")
    auth_repo = AuthenticationRepository(path=repo_path)
    initial_commits_num = len(auth_repo.list_commits())
    namespace = library.name
    target_repo_name = f"{namespace}/new_target"
    add_target_repo(
        repo_path,
        None,
        target_repo_name,
        "delegated_role",
        None,
        api_keystore,
        push=False,
    )
    # verify repositories.json was updated and that changes were committed
    # then validate the repository
    repositories_json = repositoriesdb.load_repositories_json(auth_repo)
    assert repositories_json is not None
    repositories = repositories_json["repositories"]
    assert target_repo_name in repositories
    commits = auth_repo.list_commits()
    assert len(commits) == initial_commits_num + 1
    assert commits[0].message.strip() == git_commit_message(
        "add-target", target_name=target_repo_name
    )
    signed_target_files = auth_repo.get_signed_target_files()
    assert target_repo_name in signed_target_files
    delegated_paths = auth_repo.get_delegated_role_property("paths", "delegated_role")
    assert target_repo_name in delegated_paths
    target_repo_path = library.parent / target_repo_name
    assert check_target_file(target_repo_path, target_repo_name, auth_repo)


def test_remove_target_repository_when_not_on_filesystem(
    library: Path, api_keystore: str
):
    repo_path = str(library / "auth")
    auth_repo = AuthenticationRepository(path=repo_path)
    initial_commits_num = len(auth_repo.list_commits())
    namespace = library.name
    target_repo_name = f"{namespace}/target4"
    repositories_json = repositoriesdb.load_repositories_json(auth_repo)
    assert repositories_json is not None
    repositories = repositories_json["repositories"]
    assert target_repo_name in repositories
    remove_target_repo(
        str(repo_path),
        target_repo_name,
        api_keystore,
        push=False,
    )
    # verify repositories.json was updated and that changes were committed
    # then validate the repository
    # target repo should not be in the newest repositories.json
    repositories_json = repositoriesdb.load_repositories_json(auth_repo)
    assert repositories_json is not None
    repositories = repositories_json["repositories"]
    assert target_repo_name not in repositories
    commits = auth_repo.list_commits()
    # this function is expected to commit twice
    assert len(commits) == initial_commits_num + 2
    assert commits[1].message.strip() == git_commit_message(
        "remove-target", target_name=target_repo_name
    )
    assert commits[0].message.strip() == git_commit_message(
        "remove-from-delegated-paths", target_name=target_repo_name
    )
    delegated_paths = auth_repo.get_delegated_role_property("paths", "delegated_role")
    assert target_repo_name not in delegated_paths


def test_remove_target_repository_when_on_filesystem(library: Path, api_keystore: str):
    repo_path = str(library / "auth")
    auth_repo = AuthenticationRepository(path=repo_path)
    initial_commits_num = len(auth_repo.list_commits())
    namespace = library.name
    target_repo_name = f"{namespace}/new_target"
    repositories_json = repositoriesdb.load_repositories_json(auth_repo)
    assert repositories_json is not None
    repositories = repositories_json["repositories"]
    assert Path(repo_path, TARGETS_DIRECTORY_NAME, target_repo_name).is_file()
    assert target_repo_name in repositories
    remove_target_repo(
        str(repo_path),
        target_repo_name,
        api_keystore,
        push=False,
    )
    # verify that repositories.json was updated and that changes were committed
    # then validate the repository
    # target repo should not be in the newest repositories.json
    repositories_json = repositoriesdb.load_repositories_json(auth_repo)
    assert repositories_json is not None
    repositories = repositories_json["repositories"]
    assert target_repo_name not in repositories
    commits = auth_repo.list_commits()
    # this function is expected to commit twice
    assert len(commits) == initial_commits_num + 2
    assert commits[1].message.strip() == git_commit_message(
        "remove-target", target_name=target_repo_name
    )
    assert commits[0].message.strip() == git_commit_message(
        "remove-from-delegated-paths", target_name=target_repo_name
    )
    delegated_paths = auth_repo.get_delegated_role_property("paths", "delegated_role")
    assert target_repo_name not in delegated_paths
    assert not Path(repo_path, TARGETS_DIRECTORY_NAME, target_repo_name).is_file()
