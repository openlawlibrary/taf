from pathlib import Path
import shutil

from taf.api.metadata import update_metadata_expiration_date
import pytest
from typing import Dict
from taf import repositoriesdb
from taf.api.repository import create_repository
from taf.api.targets import update_target_repos_from_repositories_json
from taf.auth_repo import AuthenticationRepository
from taf.git import GitRepository
from taf.tests.utils import copy_mirrors_json, copy_repositories_json
from taf.utils import on_rm_error
from contextlib import contextmanager
from taf.yubikey.yubikey_manager import PinManager

AUTH_REPO_NAME = "auth"


@pytest.fixture(scope="session")
def root_dir(repo_dir):
    root_dir = repo_dir / "test_repositoriesdb"
    yield root_dir
    shutil.rmtree(root_dir, onerror=on_rm_error)


@pytest.fixture(scope="session")
def target_repos(root_dir):
    repos = []
    for target in ("target1", "target2", "target3"):
        target_repo_path = root_dir / target
        target_repo_path.mkdir(parents=True)
        target_repo = GitRepository(path=target_repo_path)
        target_repo.init_repo()
        target_repo.commit_empty("Initial commit")
        repos.append(target_repo)
    return repos


@pytest.fixture(scope="session")
def auth_repo_with_targets(
    root_dir: Path,
    with_delegations_no_yubikeys_path: str,
    keystore_delegations: str,
    repositories_json_template: Dict,
    mirrors_json_path: Path,
    pin_manager: PinManager,
):
    auth_path = root_dir / AUTH_REPO_NAME
    auth_path.mkdir(exist_ok=True, parents=True)
    namespace = root_dir.name
    copy_repositories_json(repositories_json_template, namespace, auth_path)
    copy_mirrors_json(mirrors_json_path, auth_path)
    create_repository(
        str(auth_path),
        pin_manager,
        roles_key_infos=with_delegations_no_yubikeys_path,
        keystore=keystore_delegations,
        commit=True,
    )
    update_target_repos_from_repositories_json(
        str(auth_path),
        pin_manager,
        str(root_dir.parent),
        keystore_delegations,
        commit=True,
    )
    update_metadata_expiration_date(
        path=auth_path,
        pin_manager=pin_manager,
        roles=["targets"],
        keystore=keystore_delegations,
    )

    auth_reo = AuthenticationRepository(path=auth_path)
    yield auth_reo


@contextmanager
def load_repositories(auth_repo, **kwargs):
    repositoriesdb.load_repositories(auth_repo, **kwargs)
    yield
    repositoriesdb.clear_repositories_db()
