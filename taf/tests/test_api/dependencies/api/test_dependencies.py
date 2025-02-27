import pytest
from pathlib import Path
from taf.api.dependencies import add_dependency, remove_dependency
from taf.exceptions import TAFError
from taf.messages import git_commit_message
import taf.repositoriesdb as repositoriesdb
from taf.auth_repo import AuthenticationRepository
from taf.api.repository import create_repository
from taf.tests.test_api.conftest import DEPENDENCY_NAME
from taf.yubikey.yubikey_manager import PinManager


def test_setup_repositories(
    child_repo_path: Path,
    parent_repo_path: Path,
    with_delegations_no_yubikeys_path: str,
    keystore_delegations: str,
    pin_manager: PinManager,
):
    for path in (child_repo_path, parent_repo_path):
        create_repository(
            str(path),
            pin_manager,
            roles_key_infos=with_delegations_no_yubikeys_path,
            keystore=keystore_delegations,
            commit=True,
        )


def test_add_dependency_when_on_filesystem_invalid_commit(
    parent_repo_path,
    child_repo_path,
    keystore_delegations,
    pin_manager,
):
    auth_repo = AuthenticationRepository(path=parent_repo_path)
    initial_commits_num = len(auth_repo.list_pygit_commits())
    child_repository = AuthenticationRepository(path=child_repo_path)

    with pytest.raises(TAFError):
        add_dependency(
            path=str(parent_repo_path),
            pin_manager=pin_manager,
            dependency_name=child_repository.name,
            keystore=keystore_delegations,
            branch_name="main",
            out_of_band_hash="66d7f48e972f9fa25196523f469227dfcd85c994",
            no_prompt=True,
            push=False,
        )
    commits = auth_repo.list_pygit_commits()
    assert len(commits) == initial_commits_num


def test_add_dependency_when_on_filesystem(
    parent_repo_path,
    child_repo_path,
    keystore_delegations,
    pin_manager,
):
    auth_repo = AuthenticationRepository(path=parent_repo_path)
    initial_commits_num = len(auth_repo.list_pygit_commits())
    child_repository = AuthenticationRepository(path=child_repo_path)

    add_dependency(
        path=str(parent_repo_path),
        pin_manager=pin_manager,
        dependency_name=child_repository.name,
        keystore=keystore_delegations,
        branch_name=None,
        out_of_band_hash=None,
        no_prompt=True,
        push=False,
    )
    commits = auth_repo.list_pygit_commits()
    assert len(commits) == initial_commits_num + 1
    assert commits[0].message.strip() == git_commit_message(
        "add-dependency", dependency_name=child_repository.name
    )

    dependencies_json = repositoriesdb.load_dependencies_json(auth_repo)
    dependencies = dependencies_json["dependencies"]
    assert child_repository.name in dependencies
    assert dependencies[child_repository.name] == {
        "out-of-band-authentication": child_repository.head_commit().value,
        "branch": child_repository.default_branch,
    }


def test_add_dependency_when_not_on_filesystem(
    parent_repo_path, keystore_delegations, pin_manager
):
    auth_repo = AuthenticationRepository(path=parent_repo_path)
    initial_commits_num = len(auth_repo.list_pygit_commits())
    branch_name = "main"
    out_of_band_hash = "66d7f48e972f9fa25196523f469227dfcd85c994"
    add_dependency(
        path=str(parent_repo_path),
        pin_manager=pin_manager,
        dependency_name=DEPENDENCY_NAME,
        keystore=keystore_delegations,
        branch_name=branch_name,
        out_of_band_hash=out_of_band_hash,
        no_prompt=True,
        push=False,
    )
    commits = auth_repo.list_pygit_commits()
    assert len(commits) == initial_commits_num + 1
    assert commits[0].message.strip() == git_commit_message(
        "add-dependency", dependency_name=DEPENDENCY_NAME
    )

    dependencies_json = repositoriesdb.load_dependencies_json(auth_repo)
    dependencies = dependencies_json["dependencies"]
    assert DEPENDENCY_NAME in dependencies
    assert dependencies[DEPENDENCY_NAME] == {
        "out-of-band-authentication": out_of_band_hash,
        "branch": branch_name,
    }


def test_remove_dependency(
    parent_repo_path, child_repo_path, keystore_delegations, pin_manager
):
    auth_repo = AuthenticationRepository(path=parent_repo_path)
    initial_commits_num = len(auth_repo.list_pygit_commits())
    child_repository = AuthenticationRepository(path=child_repo_path)

    remove_dependency(
        path=str(parent_repo_path),
        pin_manager=pin_manager,
        dependency_name=child_repository.name,
        keystore=keystore_delegations,
        push=False,
    )
    commits = auth_repo.list_pygit_commits()
    assert len(commits) == initial_commits_num + 1
    assert commits[0].message.strip() == git_commit_message(
        "remove-dependency", dependency_name=child_repository.name
    )
    dependencies_json = repositoriesdb.load_dependencies_json(auth_repo)
    dependencies = dependencies_json["dependencies"]
    assert child_repository.name not in dependencies
