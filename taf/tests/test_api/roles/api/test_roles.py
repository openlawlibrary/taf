from pathlib import Path
from taf.api.roles import (
    add_role,
    add_role_paths,
    add_roles,
    add_signing_key,
    list_keys_of_role,
    remove_paths,
    revoke_signing_key,
)
from taf.messages import git_commit_message
from taf.auth_repo import AuthenticationRepository
from taf.tests.test_api.util import check_new_role
from taf.yubikey.yubikey_manager import PinManager


def test_add_role_when_target_is_parent(
    auth_repo: AuthenticationRepository,
    roles_keystore: str,
    pin_manager: PinManager,
):
    initial_commits_num = len(auth_repo.list_pygit_commits())
    ROLE_NAME = "new_role"
    PATHS = ["some-path1", "some-path2"]
    PARENT_NAME = "targets"
    add_role(
        path=str(auth_repo.path),
        pin_manager=pin_manager,
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
    commits = auth_repo.list_pygit_commits()
    assert len(commits) == initial_commits_num + 1
    assert commits[0].message.strip() == git_commit_message("add-role", role=ROLE_NAME)
    check_new_role(auth_repo, ROLE_NAME, PATHS, roles_keystore, PARENT_NAME)


def test_add_role_when_delegated_role_is_parent(
    auth_repo_with_delegations: AuthenticationRepository,
    roles_keystore: str,
    pin_manager: PinManager,
):
    initial_commits_num = len(auth_repo_with_delegations.list_pygit_commits())
    ROLE_NAME = "new_inner_role"
    PATHS = ["inner-path1", "inner-path2"]
    PARENT_NAME = "delegated_role"
    add_role(
        path=str(auth_repo_with_delegations.path),
        pin_manager=pin_manager,
        auth_repo=auth_repo_with_delegations,
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
    commits = auth_repo_with_delegations.list_pygit_commits()
    assert len(commits) == initial_commits_num + 1
    assert commits[0].message.strip() == git_commit_message("add-role", role=ROLE_NAME)
    check_new_role(
        auth_repo_with_delegations, ROLE_NAME, PATHS, roles_keystore, PARENT_NAME
    )


def test_add_multiple_roles(
    auth_repo: AuthenticationRepository,
    pin_manager: PinManager,
    roles_keystore: str,
    add_roles_config_json_input: str,
):
    initial_commits_num = len(auth_repo.list_pygit_commits())
    add_roles(
        path=str(auth_repo.path),
        pin_manager=pin_manager,
        keystore=roles_keystore,
        roles_key_infos=add_roles_config_json_input,
        push=False,
    )
    # with_delegations_no_yubikeys_path specification contains delegated_role and inner_role
    # definitions, so these two roles should get added to the repository
    commits = auth_repo.list_pygit_commits()
    assert len(commits) == initial_commits_num + 1
    new_roles = ["delegated_role"]
    assert commits[0].message.strip() == git_commit_message(
        "add-roles", roles=", ".join(new_roles)
    )
    target_roles = auth_repo.get_all_targets_roles()
    for role_name in new_roles:
        assert role_name in target_roles
    assert auth_repo.find_delegated_roles_parent("delegated_role") == "targets"


def test_add_role_paths(
    auth_repo_with_delegations: AuthenticationRepository,
    roles_keystore: str,
    pin_manager: PinManager,
):
    initial_commits_num = len(auth_repo_with_delegations.list_pygit_commits())
    NEW_PATHS = ["some-path3"]
    ROLE_NAME = "delegated_role"
    add_role_paths(
        path=auth_repo_with_delegations.path,
        auth_repo=auth_repo_with_delegations,
        pin_manager=pin_manager,
        paths=NEW_PATHS,
        keystore=roles_keystore,
        delegated_role=ROLE_NAME,
        push=False,
    )

    commits = auth_repo_with_delegations.list_pygit_commits()
    assert len(commits) == initial_commits_num + 1
    assert commits[0].message.strip() == git_commit_message(
        "add-role-paths", paths=", ".join(NEW_PATHS), role=ROLE_NAME
    )
    roles_paths = auth_repo_with_delegations.get_role_paths(ROLE_NAME)
    assert len(roles_paths) == 3
    assert "some-path3" in roles_paths


def test_remove_role_paths(
    auth_repo_with_delegations: AuthenticationRepository,
    roles_keystore: str,
    pin_manager: PinManager,
):
    initial_commits_num = len(auth_repo_with_delegations.list_pygit_commits())
    REMOVED_PATHS = ["dir2/path1"]
    ROLE_NAME = "delegated_role"
    remove_paths(
        path=str(auth_repo_with_delegations.path),
        pin_manager=pin_manager,
        paths=REMOVED_PATHS,
        keystore=roles_keystore,
        push=False,
    )

    commits = auth_repo_with_delegations.list_pygit_commits()
    assert len(commits) == initial_commits_num + 1
    assert commits[0].message.strip() == git_commit_message(
        "remove-role-paths", paths=", ".join(REMOVED_PATHS), role=ROLE_NAME
    )
    roles_paths = auth_repo_with_delegations.get_role_paths(ROLE_NAME)
    assert len(roles_paths) == 1
    assert REMOVED_PATHS[0] not in roles_paths


# TODO enable when remove role is reimplemented
# def test_remove_role_when_no_targets(auth_repo_with_delegations: AuthenticationRepository, roles_keystore: str):
#     initial_commits_num = len(auth_repo_with_delegations.list_pygit_commits())
#     ROLE_NAME = "inner_role"
#     remove_role(
#         path=str(auth_repo_with_delegations.path),
#         role=ROLE_NAME,
#         keystore=roles_keystore,
#         push=False,
#     )
#     commits = auth_repo_with_delegations.list_pygit_commits()
#     assert len(commits) == initial_commits_num + 1
#     assert commits[0].message.strip() == git_commit_message(
#         "remove-role", role=ROLE_NAME
#     )


# def test_remove_role_when_remove_targets(auth_repo_with_delegations: AuthenticationRepository, roles_keystore: str):
#     initial_commits_num = len(auth_repo_with_delegations.list_pygit_commits())
#     ROLE_NAME = "delegated_role"
#     # add target files which match the delegated role's paths
#     # one is a glob dir1/*
#     # the second one is dir2/path1
#     FILENAME1 = "test.txt"
#     FILENAME2 = "path1"
#     # add a new file to the targets directory, check if it was signed
#     # make sure the path was delegated to delegated_role
#     file_dir1 = auth_repo_with_delegations.path / TARGETS_DIRECTORY_NAME / "dir1"
#     file_dir2 = auth_repo_with_delegations.path / TARGETS_DIRECTORY_NAME / "dir2"
#     file_dir1.mkdir()
#     file_dir2.mkdir()
#     file_path1 = file_dir1 / FILENAME1
#     file_path1.write_text("test")
#     file_path2 = file_dir2 / FILENAME2
#     file_path2.write_text("test")
#     register_target_files(auth_repo_with_delegations.path, roles_keystore, update_snapshot_and_timestamp=True, push=False)
#     check_if_targets_signed(
#         auth_repo_with_delegations, ROLE_NAME, f"dir1/{FILENAME1}", f"dir2/{FILENAME2}"
#     )
#     commits = auth_repo_with_delegations.list_pygit_commits()
#     assert len(commits) == initial_commits_num + 1
#     remove_role(
#         path=str(auth_repo_with_delegations.path),
#         role=ROLE_NAME,
#         keystore=roles_keystore,
#         push=False,
#         remove_targets=True,
#     )
#     commits = auth_repo_with_delegations.list_pygit_commits()
#     assert len(commits) == initial_commits_num + 2
#     assert commits[0].message.strip() == git_commit_message(
#         "remove-role", role=ROLE_NAME
#     )
#     assert not file_path1.is_file()
#     assert not file_path2.is_file()


# def test_remove_role_when_keep_targets(auth_repo: AuthenticationRepository, roles_keystore: str):
#     initial_commits_num = len(auth_repo.list_pygit_commits())
#     ROLE_NAME = "new_role"
#     # add target file which matches the delegated role's paths
#     FILENAME = "some-path2"
#     # add a new file to the targets directory, check if it was signed
#     # make sure the path was delegated to delegated_role
#     file_path = auth_repo.path / TARGETS_DIRECTORY_NAME / FILENAME
#     file_path.write_text("test")
#     register_target_files(auth_repo.path, roles_keystore, write=True, push=False)
#     check_if_targets_signed(auth_repo, ROLE_NAME, FILENAME)
#     commits = auth_repo.list_pygit_commits()
#     assert len(commits) == initial_commits_num + 1
#     remove_role(
#         path=str(auth_repo.path),
#         role=ROLE_NAME,
#         keystore=roles_keystore,
#         push=False,
#         remove_targets=False,
#     )
#     commits = auth_repo.list_pygit_commits()
#     assert len(commits) == initial_commits_num + 2
#     assert commits[0].message.strip() == git_commit_message(
#         "remove-role", role=ROLE_NAME
#     )
#     assert file_path.is_file()


def test_list_keys(auth_repo: AuthenticationRepository):
    root_keys_infos = list_keys_of_role(str(auth_repo.path), "root")
    assert len(root_keys_infos) == 3
    targets_keys_infos = list_keys_of_role(str(auth_repo.path), "targets")
    assert len(targets_keys_infos) == 2
    snapshot_keys_infos = list_keys_of_role(str(auth_repo.path), "snapshot")
    assert len(snapshot_keys_infos) == 1
    timestamp_keys_infos = list_keys_of_role(str(auth_repo.path), "timestamp")
    assert len(timestamp_keys_infos) == 1


def test_add_signing_key(
    auth_repo: AuthenticationRepository, roles_keystore: str, pin_manager: PinManager
):
    auth_repo = AuthenticationRepository(path=auth_repo.path)
    initial_commits_num = len(auth_repo.list_pygit_commits())
    # for testing purposes, add targets signing key to timestamp and snapshot roles
    pub_key_path = Path(roles_keystore, "targets1.pub")
    COMMIT_MSG = "Add new timestamp and snapshot signing key"
    add_signing_key(
        path=str(auth_repo.path),
        pin_manager=pin_manager,
        pub_key_path=str(pub_key_path),
        roles=["timestamp", "snapshot"],
        keystore=roles_keystore,
        push=False,
        commit_msg=COMMIT_MSG,
    )
    commits = auth_repo.list_pygit_commits()
    assert len(commits) == initial_commits_num + 1
    assert commits[0].message.strip() == COMMIT_MSG
    timestamp_keys_infos = list_keys_of_role(str(auth_repo.path), "timestamp")
    assert len(timestamp_keys_infos) == 2
    snapshot_keys_infos = list_keys_of_role(str(auth_repo.path), "snapshot")
    assert len(snapshot_keys_infos) == 2


def test_revoke_signing_key(
    auth_repo: AuthenticationRepository, roles_keystore: str, pin_manager: PinManager
):
    auth_repo = AuthenticationRepository(path=auth_repo.path)
    targest_keyids = auth_repo.get_keyids_of_role("targets")
    key_to_remove = targest_keyids[-1]
    initial_commits_num = len(auth_repo.list_pygit_commits())
    targets_keys_infos = list_keys_of_role(str(auth_repo.path), "targets")
    assert len(targets_keys_infos) == 2
    COMMIT_MSG = "Revoke a targets key"
    revoke_signing_key(
        path=str(auth_repo.path),
        pin_manager=pin_manager,
        key_id=key_to_remove,
        keystore=roles_keystore,
        push=False,
        commit_msg=COMMIT_MSG,
    )
    commits = auth_repo.list_pygit_commits()
    assert len(commits) == initial_commits_num + 1
    targets_keys_infos = list_keys_of_role(str(auth_repo.path), "targets")
    assert len(targets_keys_infos) == 1
    assert commits[0].message.strip() == COMMIT_MSG
