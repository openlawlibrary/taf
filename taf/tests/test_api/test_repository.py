from pathlib import Path
from taf.api.repository import create_repository
from taf.auth_repo import AuthenticationRepository
from taf.updater.updater import validate_repository
from tuf.repository_tool import METADATA_DIRECTORY_NAME, TARGETS_DIRECTORY_NAME


def _check_repo_initialization_successful(auth_repo):
    repo_root_path = Path(auth_repo.path)
    metadata_dir = repo_root_path / METADATA_DIRECTORY_NAME
    targets_dir = repo_root_path / TARGETS_DIRECTORY_NAME
    assert auth_repo.is_git_repository_root is True
    assert metadata_dir.is_dir() is True
    # verify that metadata files were created
    for role in ("root", "targets", "snapshot", "timestamp"):
        assert (metadata_dir / f"{role}.json").is_file() is True

    assert targets_dir.is_dir() is True
    commits = auth_repo.list_commits()
    assert len(commits) == 1


def test_create_repository_no_delegations(
    auth_repo, no_yubikeys_path, api_keystore
):
    repo_path = str(auth_repo.path)
    create_repository(
        repo_path,
        roles_key_infos=no_yubikeys_path,
        keystore=api_keystore,
        commit=True,
        commit_msg="Initial commit",
    )
    _check_repo_initialization_successful(auth_repo)

    validate_repository(repo_path)


def test_create_repository_no_delegations_with_test_flag(
    auth_repo, no_yubikeys_path, api_keystore
):
    repo_path = str(auth_repo.path)
    create_repository(
        repo_path,
        roles_key_infos=no_yubikeys_path,
        keystore=api_keystore,
        commit=True,
        commit_msg="Initial commit",
        test=True,
    )

    _check_repo_initialization_successful(auth_repo)
    validate_repository(repo_path)