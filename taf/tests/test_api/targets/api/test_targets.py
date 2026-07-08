from pathlib import Path

from taf.constants import TARGETS_DIRECTORY_NAME
from taf.messages import git_commit_message
import taf.repositoriesdb as repositoriesdb
from taf.auth_repo import AuthenticationRepository

from taf.api.targets import (
    add_target_repo,
    register_target_files,
    update_and_sign_targets,
    update_target_repos_from_repositories_json,
)
from taf.tests.test_api.util import (
    check_if_targets_signed,
    check_role_scheme,
    check_target_file,
)
from taf.yubikey.yubikey_manager import PinManager

AUTH_REPO_NAME = "auth"


def normalize_to_windows_file_line_endings(file_path):
    """Utility function to normalize file line endings to Windows style (CRLF)."""
    with open(file_path, "rb") as open_file:
        content = open_file.read()
    replaced_content = normalize_windows_line_endings(content)
    if replaced_content != content:
        with open(file_path, "wb") as open_file:
            open_file.write(replaced_content)


def normalize_windows_line_endings(file_content):
    """Normalize line endings to Windows style (CRLF)."""
    WINDOWS_LINE_ENDING = b"\n"
    UNIX_LINE_ENDING = b"\r\n"
    replaced_content = file_content.replace(
        WINDOWS_LINE_ENDING, UNIX_LINE_ENDING
    ).rstrip(UNIX_LINE_ENDING)
    return replaced_content


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


def test_register_targets_when_file_modified_and_line_endings_are_touched(
    auth_repo_when_add_repositories_json: AuthenticationRepository,
    pin_manager: PinManager,
    library: Path,
    keystore_delegations: str,
):
    repo_path = library / "auth"
    initial_commits_num = len(auth_repo_when_add_repositories_json.list_pygit_commits())

    dir1_file_path = repo_path / TARGETS_DIRECTORY_NAME / "dir1" / "path1"
    dir1_file_path.parent.mkdir(parents=True, exist_ok=True)
    dir1_file_path.write_text("test\ntest")
    dir2_file_path = repo_path / TARGETS_DIRECTORY_NAME / "dir2" / "path2"
    dir2_file_path.parent.mkdir(parents=True, exist_ok=True)
    dir2_file_path.write_text("test\ntest")

    register_target_files(
        repo_path,
        pin_manager,
        keystore_delegations,
        update_snapshot_and_timestamp=True,
        push=False,
    )
    # change the file content
    dir2_file_path.write_text("test modified\ntest modified")
    # convert test_txt_filepath to unix style endings
    normalize_to_windows_file_line_endings(str(dir1_file_path))
    normalize_to_windows_file_line_endings(str(dir2_file_path))

    expected_delegated_role_version = auth_repo_when_add_repositories_json._signed_obj(
        "delegated_role"
    ).version
    expected_inner_role_version = auth_repo_when_add_repositories_json._signed_obj(
        "inner_role"
    ).version
    register_target_files(
        repo_path,
        pin_manager,
        keystore_delegations,
        update_snapshot_and_timestamp=True,
        push=False,
    )

    actual_delegated_role_version = auth_repo_when_add_repositories_json._signed_obj(
        "delegated_role"
    ).version
    actual_inner_role_version = auth_repo_when_add_repositories_json._signed_obj(
        "inner_role"
    ).version

    check_if_targets_signed(
        auth_repo_when_add_repositories_json, "inner_role", "dir2/path2"
    )
    # verify that other delegated role was not touched
    # even though we've used CRLF
    assert (
        expected_delegated_role_version == actual_delegated_role_version
    ), "Expected delegated_role to not be updated, but it was"
    # verify "inner_role" signed
    assert (
        expected_inner_role_version + 1 == actual_inner_role_version
    ), "Expected inner_role to be updated, but it was not"

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


def test_update_and_sign_targets(
    auth_repo_when_add_repositories_json: AuthenticationRepository,
    pin_manager: PinManager,
    library: Path,
    keystore_delegations: str,
):
    """update_and_sign_targets had a bug where it called register_target_files
    with positional arguments that no longer lined up after the scheme
    parameter was removed, silently corrupting later arguments. This is the
    first direct test of this function.
    """
    repo_path = library / "auth"
    initial_commits_num = len(auth_repo_when_add_repositories_json.list_pygit_commits())
    namespace = library.name
    update_and_sign_targets(
        str(repo_path),
        pin_manager,
        str(library.parent),
        ["type1"],
        keystore_delegations,
        None,
        push=False,
    )
    target_repo_name = f"{namespace}/target1"
    target_repo_path = library.parent / target_repo_name
    assert check_target_file(
        target_repo_path, target_repo_name, auth_repo_when_add_repositories_json
    )
    commits = auth_repo_when_add_repositories_json.list_pygit_commits()
    assert len(commits) == initial_commits_num + 1


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


def test_add_target_repo_applies_requested_scheme_when_creating_new_role(
    auth_repo_when_add_repositories_json: AuthenticationRepository,
    pin_manager: PinManager,
    library: Path,
    roles_keystore: str,
):
    """When add_target_repo has to create a brand-new role for the target,
    it must forward the scheme it was called with to add_role, instead of
    hardcoding the RSA default regardless of what was requested.

    Uses roles_keystore (an ephemeral, per-module copy that gets deleted
    after the test module runs) rather than keystore_delegations directly,
    since this test generates a brand-new key and keystore_delegations is
    a shared, persistent fixture data directory.
    """
    requested_scheme = "rsassa-pss-sha256"
    ROLE_NAME = "role_for_custom_scheme"
    repo_path = str(library / "auth")
    namespace = library.name
    target_repo_name = f"{namespace}/target_with_new_role"
    add_target_repo(
        repo_path,
        pin_manager,
        None,
        target_repo_name,
        ROLE_NAME,
        None,
        roles_keystore,
        paths=[target_repo_name],
        keys_number=1,
        threshold=1,
        yubikey=False,
        scheme=requested_scheme,
        push=False,
        should_create_new_role=True,
        skip_prompt=True,
    )

    check_role_scheme(auth_repo_when_add_repositories_json, ROLE_NAME, requested_scheme)


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
