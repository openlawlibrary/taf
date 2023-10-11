import shutil
import uuid
from pathlib import Path
from typing import List
from taf.api.roles import (
    add_role,
    add_role_paths,
    add_roles,
    add_signing_key,
    list_keys_of_role,
    remove_paths,
    remove_role,
)
from taf.api.targets import register_target_files
from taf.messages import git_commit_message
from taf.auth_repo import AuthenticationRepository
from pytest import fixture
from taf.api.repository import create_repository
from taf.tests.conftest import CLIENT_DIR_PATH, KEYSTORES_PATH
from taf.tests.test_api.conftest import KEYSTORE_PATH
from taf.tests.test_api.util import check_if_targets_signed
from taf.utils import on_rm_error
from tuf.repository_tool import TARGETS_DIRECTORY_NAME


AUTH_REPO_NAME = "auth"


@fixture(scope="module")
def auth_repo_path():
    random_name = str(uuid.uuid4())
    root_dir = CLIENT_DIR_PATH / random_name
    auth_path = root_dir / AUTH_REPO_NAME
    auth_path.mkdir(exist_ok=True, parents=True)
    yield auth_path
    shutil.rmtree(root_dir, onerror=on_rm_error)


@fixture(scope="module")
def roles_keystore():
    # set up a keystore by copying the api keystore
    # new keystore files are expected to be created and store to this directory
    # it will be removed once this test's execution is done
    # Create the destination folder if it doesn't exist
    roles_keystore = KEYSTORES_PATH / "roles_keystore"
    if roles_keystore.is_dir():
        shutil.rmtree(str(roles_keystore))

    # Copy the contents of the source folder to the destination folder
    shutil.copytree(KEYSTORE_PATH, str(roles_keystore))
    yield str(roles_keystore)
    shutil.rmtree(str(roles_keystore))


def test_setup_auth_repo(
    auth_repo_path: Path,
    no_yubikeys_path: str,
    roles_keystore: str,
):
    create_repository(
        str(auth_repo_path),
        roles_key_infos=no_yubikeys_path,
        keystore=roles_keystore,
        commit=True,
    )


def test_add_role_when_target_is_parent(auth_repo_path: Path, roles_keystore: str):
    auth_repo = AuthenticationRepository(path=auth_repo_path)
    initial_commits_num = len(auth_repo.list_commits())
    ROLE_NAME = "new_role"
    PATHS = ["some-path1", "some-path2"]
    PARENT_NAME = "targets"
    add_role(
        path=str(auth_repo_path),
        auth_repo=auth_repo,
        role=ROLE_NAME,
        parent_role=PARENT_NAME,
        paths=PATHS,
        keys_number=2,
        threshold=1,
        yubikey=False,
        keystore=roles_keystore,
        push=False,
        skip_prompt=True,
    )
    commits = auth_repo.list_commits()
    assert len(commits) == initial_commits_num + 1
    assert commits[0].message.strip() == git_commit_message("add-role", role=ROLE_NAME)
    _check_new_role(auth_repo, ROLE_NAME, PATHS, roles_keystore, PARENT_NAME)


def test_add_role_when_delegated_role_is_parent(
    auth_repo_path: Path, roles_keystore: str
):
    auth_repo = AuthenticationRepository(path=auth_repo_path)
    initial_commits_num = len(auth_repo.list_commits())
    ROLE_NAME = "new_inner_role"
    PATHS = ["inner-path1", "inner-path2"]
    PARENT_NAME = "new_role"
    add_role(
        path=str(auth_repo_path),
        auth_repo=auth_repo,
        role=ROLE_NAME,
        parent_role=PARENT_NAME,
        paths=PATHS,
        keys_number=2,
        threshold=1,
        yubikey=False,
        keystore=roles_keystore,
        push=False,
        skip_prompt=True,
    )
    commits = auth_repo.list_commits()
    assert len(commits) == initial_commits_num + 1
    assert commits[0].message.strip() == git_commit_message("add-role", role=ROLE_NAME)
    _check_new_role(auth_repo, ROLE_NAME, PATHS, roles_keystore, PARENT_NAME)


def test_add_multiple_roles(
    auth_repo_path: Path, roles_keystore: str, with_delegations_no_yubikeys_path: str
):
    auth_repo = AuthenticationRepository(path=auth_repo_path)
    initial_commits_num = len(auth_repo.list_commits())
    add_roles(
        path=str(auth_repo_path),
        keystore=roles_keystore,
        roles_key_infos=with_delegations_no_yubikeys_path,
        push=False,
    )
    # with_delegations_no_yubikeys_path specification contains delegated_role and inner_role
    # definitions, so these two roles should get added to the repository
    commits = auth_repo.list_commits()
    assert len(commits) == initial_commits_num + 1
    new_roles = ["delegated_role", "inner_role"]
    assert commits[0].message.strip() == git_commit_message(
        "add-roles", roles=", ".join(new_roles)
    )
    target_roles = auth_repo.get_all_targets_roles()
    for role_name in new_roles:
        assert role_name in target_roles
    assert auth_repo.find_delegated_roles_parent("delegated_role") == "targets"
    assert auth_repo.find_delegated_roles_parent("inner_role") == "delegated_role"


def test_add_role_paths(auth_repo_path: Path, roles_keystore: str):
    auth_repo = AuthenticationRepository(path=auth_repo_path)
    initial_commits_num = len(auth_repo.list_commits())
    NEW_PATHS = ["some-path3"]
    ROLE_NAME = "new_role"
    add_role_paths(
        auth_repo=auth_repo,
        paths=NEW_PATHS,
        keystore=roles_keystore,
        delegated_role="new_role",
        push=False,
    )

    commits = auth_repo.list_commits()
    assert len(commits) == initial_commits_num + 1
    assert commits[0].message.strip() == git_commit_message(
        "add-role-paths", paths=", ".join(NEW_PATHS), role=ROLE_NAME
    )
    roles_paths = auth_repo.get_role_paths(ROLE_NAME)
    assert len(roles_paths) == 3
    assert "some-path3" in roles_paths


def test_remove_role_paths(auth_repo_path: Path, roles_keystore: str):
    auth_repo = AuthenticationRepository(path=auth_repo_path)
    initial_commits_num = len(auth_repo.list_commits())
    REMOVED_PATHS = ["some-path1"]
    ROLE_NAME = "new_role"
    remove_paths(
        path=str(auth_repo_path),
        paths=REMOVED_PATHS,
        keystore=roles_keystore,
        push=False,
    )

    commits = auth_repo.list_commits()
    assert len(commits) == initial_commits_num + 1
    assert commits[0].message.strip() == git_commit_message(
        "remove-role-paths", paths=", ".join(REMOVED_PATHS), role=ROLE_NAME
    )
    roles_paths = auth_repo.get_role_paths(ROLE_NAME)
    assert len(roles_paths) == 2
    assert "some-path1" not in roles_paths


def test_remove_role_when_no_targets(auth_repo_path: Path, roles_keystore: str):
    auth_repo = AuthenticationRepository(path=auth_repo_path)
    initial_commits_num = len(auth_repo.list_commits())
    ROLE_NAME = "inner_role"
    remove_role(
        path=str(auth_repo_path),
        role=ROLE_NAME,
        keystore=roles_keystore,
        push=False,
    )
    commits = auth_repo.list_commits()
    assert len(commits) == initial_commits_num + 1
    assert commits[0].message.strip() == git_commit_message(
        "remove-role", role=ROLE_NAME
    )


def test_remove_role_when_remove_targets(auth_repo_path: Path, roles_keystore: str):
    auth_repo = AuthenticationRepository(path=auth_repo_path)
    initial_commits_num = len(auth_repo.list_commits())
    ROLE_NAME = "delegated_role"
    # add target files which match the delegated role's paths
    # one is a glob dir1/*
    # the second one is dir2/path1
    FILENAME1 = "test.txt"
    FILENAME2 = "path1"
    # add a new file to the targets directory, check if it was signed
    # make sure the path was delegated to delegated_role
    file_dir1 = auth_repo_path / TARGETS_DIRECTORY_NAME / "dir1"
    file_dir2 = auth_repo_path / TARGETS_DIRECTORY_NAME / "dir2"
    file_dir1.mkdir()
    file_dir2.mkdir()
    file_path1 = file_dir1 / FILENAME1
    file_path1.write_text("test")
    file_path2 = file_dir2 / FILENAME2
    file_path2.write_text("test")
    register_target_files(auth_repo_path, roles_keystore, write=True, push=False)
    check_if_targets_signed(
        auth_repo, ROLE_NAME, f"dir1/{FILENAME1}", f"dir2/{FILENAME2}"
    )
    commits = auth_repo.list_commits()
    assert len(commits) == initial_commits_num + 1
    remove_role(
        path=str(auth_repo_path),
        role=ROLE_NAME,
        keystore=roles_keystore,
        push=False,
        remove_targets=True,
    )
    commits = auth_repo.list_commits()
    assert len(commits) == initial_commits_num + 2
    assert commits[0].message.strip() == git_commit_message(
        "remove-role", role=ROLE_NAME
    )
    assert not file_path1.is_file()
    assert not file_path2.is_file()


def test_remove_role_when_keep_targets(auth_repo_path: Path, roles_keystore: str):
    auth_repo = AuthenticationRepository(path=auth_repo_path)
    initial_commits_num = len(auth_repo.list_commits())
    ROLE_NAME = "new_role"
    # add target file which matches the delegated role's paths
    FILENAME = "some-path2"
    # add a new file to the targets directory, check if it was signed
    # make sure the path was delegated to delegated_role
    file_path = auth_repo_path / TARGETS_DIRECTORY_NAME / FILENAME
    file_path.write_text("test")
    register_target_files(auth_repo_path, roles_keystore, write=True, push=False)
    check_if_targets_signed(auth_repo, ROLE_NAME, FILENAME)
    commits = auth_repo.list_commits()
    assert len(commits) == initial_commits_num + 1
    remove_role(
        path=str(auth_repo_path),
        role=ROLE_NAME,
        keystore=roles_keystore,
        push=False,
        remove_targets=False,
    )
    commits = auth_repo.list_commits()
    assert len(commits) == initial_commits_num + 2
    assert commits[0].message.strip() == git_commit_message(
        "remove-role", role=ROLE_NAME
    )
    assert file_path.is_file()


def test_list_keys(auth_repo_path: Path):
    root_keys_infos = list_keys_of_role(str(auth_repo_path), "root")
    assert len(root_keys_infos) == 3
    targets_keys_infos = list_keys_of_role(str(auth_repo_path), "targets")
    assert len(targets_keys_infos) == 2
    snapshot_keys_infos = list_keys_of_role(str(auth_repo_path), "snapshot")
    assert len(snapshot_keys_infos) == 1
    timestamp_keys_infos = list_keys_of_role(str(auth_repo_path), "timestamp")
    assert len(timestamp_keys_infos) == 1


def test_add_signing_key(auth_repo_path: Path, roles_keystore: str):
    auth_repo = AuthenticationRepository(path=auth_repo_path)
    initial_commits_num = len(auth_repo.list_commits())
    # for testing purposes, add targets signing key to timestamp and snapshot roles
    pub_key_path = Path(roles_keystore, "targets1.pub")
    COMMIT_MSG = "Add new timestamp and snapshot signing key"
    add_signing_key(
        path=str(auth_repo_path),
        pub_key_path=str(pub_key_path),
        roles=["timestamp", "snapshot"],
        keystore=roles_keystore,
        push=False,
        commit_msg=COMMIT_MSG,
    )
    commits = auth_repo.list_commits()
    assert len(commits) == initial_commits_num + 1
    assert commits[0].message.strip() == COMMIT_MSG
    timestamp_keys_infos = list_keys_of_role(str(auth_repo_path), "timestamp")
    assert len(timestamp_keys_infos) == 2
    snapshot_keys_infos = list_keys_of_role(str(auth_repo_path), "snapshot")
    assert len(snapshot_keys_infos) == 2


def _check_new_role(
    auth_repo: AuthenticationRepository,
    role_name: str,
    paths: List[str],
    keystore_path: str,
    parent_name: str,
):
    # check if keys were created
    assert Path(keystore_path, f"{role_name}1").is_file()
    assert Path(keystore_path, f"{role_name}2").is_file()
    assert Path(keystore_path, f"{role_name}1.pub").is_file()
    assert Path(keystore_path, f"{role_name}2.pub").is_file()
    target_roles = auth_repo.get_all_targets_roles()
    assert role_name in target_roles
    assert auth_repo.find_delegated_roles_parent(role_name) == parent_name
    roles_paths = auth_repo.get_role_paths(role_name)
    assert roles_paths == paths
