from pathlib import Path

from taf.constants import TARGETS_DIRECTORY_NAME
from taf.messages import git_commit_message
import taf.repositoriesdb as repositoriesdb
from taf.auth_repo import AuthenticationRepository

from taf.api.targets import (
    add_target_repo,
    register_target_files,
    update_target_repos_from_repositories_json,
)
from taf.tests.test_api.util import (
    check_if_targets_signed,
    check_target_file,
)
from taf.yubikey.yubikey_manager import PinManager


AUTH_REPO_NAME = "auth"


def test_register_targets_when_file_added(
    auth_repo_when_add_repositories_json: AuthenticationRepository,
    pin_manager: PinManager,
    library: Path,
    keystore_delegations: str,
):
    repo_path = library / "auth"
    initial_commits_num = len(auth_repo_when_add_repositories_json.list_pygit_commits())
    FILENAME = "test.txt"
    # add a new file to the targets directory, check if it was signed
    file_path = repo_path / TARGETS_DIRECTORY_NAME / FILENAME
    file_path.write_text("test")
    register_target_files(
        repo_path,
        pin_manager,
        keystore_delegations,
        update_snapshot_and_timestamp=True,
        push=False,
    )
    check_if_targets_signed(auth_repo_when_add_repositories_json, "targets", FILENAME)
    commits = auth_repo_when_add_repositories_json.list_pygit_commits()
    assert len(commits) == initial_commits_num + 1
    assert commits[0].message.strip() == git_commit_message("update-targets")


def test_register_targets_when_file_removed(
    auth_repo_when_add_repositories_json: AuthenticationRepository,
    pin_manager: PinManager,
    library: Path,
    keystore_delegations: str,
):
    repo_path = library / "auth"
    initial_commits_num = len(auth_repo_when_add_repositories_json.list_pygit_commits())
    FILENAME = "test.txt"
    # add a new file to the targets directory, check if it was signed
    file_path = repo_path / TARGETS_DIRECTORY_NAME / FILENAME
    file_path.write_text("test")
    register_target_files(
        repo_path,
        pin_manager,
        keystore_delegations,
        update_snapshot_and_timestamp=True,
        push=False,
    )
    file_path.unlink()
    register_target_files(
        repo_path,
        pin_manager,
        keystore_delegations,
        update_snapshot_and_timestamp=True,
        push=False,
    )
    signed_target_files = auth_repo_when_add_repositories_json.get_signed_target_files()
    assert FILENAME not in signed_target_files
    commits = auth_repo_when_add_repositories_json.list_pygit_commits()
    assert len(commits) == initial_commits_num + 2
    assert commits[0].message.strip() == git_commit_message("update-targets")


def test_update_target_repos_from_repositories_json(
    auth_repo_when_add_repositories_json: AuthenticationRepository,
    pin_manager: PinManager,
    library: Path,
    keystore_delegations: str,
):
    repo_path = library / "auth"
    initial_commits_num = len(auth_repo_when_add_repositories_json.list_pygit_commits())
    namespace = library.name
    update_target_repos_from_repositories_json(
        str(repo_path),
        pin_manager,
        str(library.parent),
        keystore_delegations,
        push=False,
    )
    # this should create target files and save commit and branch to them, then sign
    for name in ("target1", "target2", "target3"):
        target_repo_name = f"{namespace}/{name}"
        target_repo_path = library.parent / target_repo_name
        assert check_target_file(
            target_repo_path, target_repo_name, auth_repo_when_add_repositories_json
        )
    commits = auth_repo_when_add_repositories_json.list_pygit_commits()
    assert len(commits) == initial_commits_num + 1
    assert commits[0].message.strip() == git_commit_message("update-targets")


def test_add_target_repository_when_not_on_filesystem(
    auth_repo_when_add_repositories_json: AuthenticationRepository,
    pin_manager: PinManager,
    library: Path,
    keystore_delegations: str,
):
    repo_path = str(library / "auth")
    initial_commits_num = len(auth_repo_when_add_repositories_json.list_pygit_commits())
    namespace = library.name
    target_repo_name = f"{namespace}/target4"
    add_target_repo(
        str(repo_path),
        pin_manager,
        None,
        target_repo_name,
        "delegated_role",
        None,
        keystore_delegations,
        push=False,
        should_create_new_role=True,
    )
    # verify repositories.json was updated and that changes were committed
    # then validate the repository
    repositories_json = repositoriesdb.load_repositories_json(
        auth_repo_when_add_repositories_json
    )
    assert repositories_json is not None
    repositories = repositories_json["repositories"]
    assert target_repo_name in repositories
    commits = auth_repo_when_add_repositories_json.list_pygit_commits()
    assert len(commits) == initial_commits_num + 2
    assert commits[0].message.strip() == git_commit_message(
        "add-target", target_name=target_repo_name
    )
    delegated_paths = auth_repo_when_add_repositories_json.get_paths_of_role(
        "delegated_role"
    )
    assert target_repo_name in delegated_paths


def test_add_target_repository_when_on_filesystem(
    auth_repo_when_add_repositories_json: AuthenticationRepository,
    pin_manager: PinManager,
    library: Path,
    keystore_delegations: str,
):
    repo_path = str(library / "auth")
    initial_commits_num = len(auth_repo_when_add_repositories_json.list_pygit_commits())
    namespace = library.name
    target_repo_name = f"{namespace}/new_target"
    add_target_repo(
        repo_path,
        pin_manager,
        None,
        target_repo_name,
        "delegated_role",
        None,
        keystore_delegations,
        push=False,
        should_create_new_role=True,
    )
    # verify repositories.json was updated and that changes were committed
    # then validate the repository
    repositories_json = repositoriesdb.load_repositories_json(
        auth_repo_when_add_repositories_json
    )
    assert repositories_json is not None
    repositories = repositories_json["repositories"]
    assert target_repo_name in repositories
    commits = auth_repo_when_add_repositories_json.list_pygit_commits()
    assert len(commits) == initial_commits_num + 2
    assert commits[0].message.strip() == git_commit_message(
        "add-target", target_name=target_repo_name
    )
    delegated_paths = auth_repo_when_add_repositories_json.get_paths_of_role(
        "delegated_role"
    )
    assert target_repo_name in delegated_paths


# def test_remove_target_repository_when_not_on_filesystem(
#     auth_repo_when_add_repositories_json: AuthenticationRepository,
#     library: Path,
#     keystore_delegations: str,
# ):
#     repo_path = str(library / "auth")
#     initial_commits_num = len(auth_repo_when_add_repositories_json.list_pygit_commits())
#     namespace = library.name
#     target_repo_name = f"{namespace}/target4"
#     repositories_json = repositoriesdb.load_repositories_json(
#         auth_repo_when_add_repositories_json
#     )
#     assert repositories_json is not None
#     repositories = repositories_json["repositories"]
#     assert target_repo_name in repositories
#     remove_target_repo(
#         str(repo_path),
#         target_repo_name,
#         keystore_delegations,
#         push=False,
#     )
#     # verify repositories.json was updated and that changes were committed
#     # then validate the repository
#     # target repo should not be in the newest repositories.json
#     repositories_json = repositoriesdb.load_repositories_json(
#         auth_repo_when_add_repositories_json
#     )
#     assert repositories_json is not None
#     repositories = repositories_json["repositories"]
#     assert target_repo_name not in repositories
#     commits = auth_repo_when_add_repositories_json.list_pygit_commits()
#     # this function is expected to commit twice
#     assert len(commits) == initial_commits_num + 2
#     assert commits[1].message.strip() == git_commit_message(
#         "remove-target", target_name=target_repo_name
#     )
#     assert commits[0].message.strip() == git_commit_message(
#         "remove-from-delegated-paths", target_name=target_repo_name
#     )
#     delegated_paths = auth_repo_when_add_repositories_json.get_paths_of_role(
#         "delegated_role"
#     )
#     assert target_repo_name not in delegated_paths


# def test_remove_target_repository_when_on_filesystem(
#     auth_repo_when_add_repositories_json: AuthenticationRepository,
#     library: Path,
#     keystore_delegations: str,
# ):
#     repo_path = str(library / "auth")
#     initial_commits_num = len(auth_repo_when_add_repositories_json.list_pygit_commits())
#     namespace = library.name
#     target_repo_name = f"{namespace}/new_target"
#     repositories_json = repositoriesdb.load_repositories_json(
#         auth_repo_when_add_repositories_json
#     )
#     assert repositories_json is not None
#     repositories = repositories_json["repositories"]
#     assert target_repo_name in repositories
#     remove_target_repo(
#         str(repo_path),
#         target_repo_name,
#         keystore_delegations,
#         push=False,
#     )
#     # verify that repositories.json was updated and that changes were committed
#     # then validate the repository
#     # target repo should not be in the newest repositories.json
#     repositories_json = repositoriesdb.load_repositories_json(
#         auth_repo_when_add_repositories_json
#     )
#     assert repositories_json is not None
#     repositories = repositories_json["repositories"]
#     assert target_repo_name not in repositories
#     commits = auth_repo_when_add_repositories_json.list_pygit_commits()
#     # this function is expected to commit twice
#     assert len(commits) == initial_commits_num + 2
#     assert commits[1].message.strip() == git_commit_message(
#         "remove-target", target_name=target_repo_name
#     )
#     assert commits[0].message.strip() == git_commit_message(
#         "remove-from-delegated-paths", target_name=target_repo_name
#     )
#     delegated_paths = auth_repo_when_add_repositories_json.get_paths_of_role(
#         "delegated_role"
#     )
#     assert target_repo_name not in delegated_paths
#     assert not Path(repo_path, TARGETS_DIRECTORY_NAME, target_repo_name).is_file()
