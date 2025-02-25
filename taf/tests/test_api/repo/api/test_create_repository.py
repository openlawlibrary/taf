from pathlib import Path

from taf.constants import METADATA_DIRECTORY_NAME, TARGETS_DIRECTORY_NAME
from typing import Dict
from taf.api.repository import create_repository
from taf.auth_repo import AuthenticationRepository
from taf.messages import git_commit_message
from taf.tests.test_api.util import (
    check_if_targets_signed,
)
from taf.tests.utils import copy_mirrors_json, copy_repositories_json
from taf.updater.updater import validate_repository
from taf.yubikey.yubikey_manager import PinManager


def _check_repo_initialization_successful(
    auth_repo: AuthenticationRepository, is_targets_initialized=True
):
    repo_root_path = auth_repo.path
    metadata_dir = repo_root_path / METADATA_DIRECTORY_NAME
    targets_dir = repo_root_path / TARGETS_DIRECTORY_NAME
    assert auth_repo.is_git_repository_root is True
    assert metadata_dir.is_dir() is True
    # verify that metadata files were created
    for role in ("root", "targets", "snapshot", "timestamp"):
        assert (metadata_dir / f"{role}.json").is_file() is True

    commits = auth_repo.list_pygit_commits()
    if is_targets_initialized:
        assert targets_dir.is_dir() is True
        assert len(commits) == 2
        assert commits[0].message.strip() == git_commit_message("update-targets")
        assert commits[1].message.strip() == git_commit_message("create-repo")
    else:
        assert len(commits) == 1
        assert commits[0].message.strip() == git_commit_message("create-repo")


def test_create_repository_when_no_delegations(
    auth_repo_path: Path,
    with_delegations_no_yubikeys_path: str,
    keystore_delegations: str,
    pin_manager: PinManager,
):
    repo_path = str(auth_repo_path)
    create_repository(
        repo_path,
        pin_manager,
        roles_key_infos=with_delegations_no_yubikeys_path,
        keystore=keystore_delegations,
        commit=True,
    )
    auth_repo = AuthenticationRepository(path=repo_path)
    _check_repo_initialization_successful(auth_repo, is_targets_initialized=False)
    assert auth_repo.is_test_repo is False
    validate_repository(repo_path)


def test_create_repository_when_no_delegations_with_test_flag(
    auth_repo_path: Path,
    with_delegations_no_yubikeys_path: str,
    keystore_delegations: str,
    pin_manager: PinManager,
):
    repo_path = str(auth_repo_path)
    create_repository(
        repo_path,
        pin_manager,
        roles_key_infos=with_delegations_no_yubikeys_path,
        keystore=keystore_delegations,
        commit=True,
        test=True,
    )

    auth_repo = AuthenticationRepository(path=repo_path)
    _check_repo_initialization_successful(auth_repo, is_targets_initialized=True)
    assert auth_repo.is_test_repo is True
    validate_repository(repo_path)


def test_create_repository_when_delegations(
    auth_repo_path: Path,
    with_delegations_no_yubikeys_path: str,
    keystore_delegations: str,
    pin_manager: PinManager,
):
    repo_path = str(auth_repo_path)
    create_repository(
        str(auth_repo_path),
        pin_manager,
        roles_key_infos=with_delegations_no_yubikeys_path,
        keystore=keystore_delegations,
        commit=True,
    )

    auth_repo = AuthenticationRepository(path=auth_repo_path)
    _check_repo_initialization_successful(auth_repo, is_targets_initialized=False)
    targets_roles = auth_repo.get_all_targets_roles()
    for role in ("targets", "delegated_role", "inner_role"):
        assert role in targets_roles
    validate_repository(repo_path)


def test_create_repository_when_add_repositories_json(
    auth_repo_path: Path,
    with_delegations_no_yubikeys_path: str,
    keystore_delegations: str,
    repositories_json_template: Dict,
    mirrors_json_path: Path,
    pin_manager: PinManager,
):
    repo_path = str(auth_repo_path)
    namespace = auth_repo_path.parent.name
    copy_repositories_json(repositories_json_template, namespace, auth_repo_path)
    copy_mirrors_json(mirrors_json_path, auth_repo_path)

    create_repository(
        repo_path,
        pin_manager,
        roles_key_infos=with_delegations_no_yubikeys_path,
        keystore=keystore_delegations,
        commit=True,
    )

    auth_repo = AuthenticationRepository(path=auth_repo_path)
    _check_repo_initialization_successful(auth_repo, is_targets_initialized=True)
    targets_roles = auth_repo.get_all_targets_roles()
    for role in ("targets", "delegated_role", "inner_role"):
        assert role in targets_roles
    check_if_targets_signed(auth_repo, "targets", "repositories.json", "mirrors.json")
    # we are not validating target repositories, just the authentication repository
    validate_repository(repo_path, excluded_target_globs="*")
