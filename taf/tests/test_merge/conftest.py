import json
import shutil
import uuid

import pytest

from taf.api.repository import create_repository
from taf.api.targets import register_target_files
from taf.auth_repo import AuthenticationRepository
from taf.git import GitRepository
from taf.tests.conftest import NO_YUBIKEYS_INPUT
from taf.utils import on_rm_error


@pytest.fixture
def merge_root(repo_dir):
    root = repo_dir / f"test_merge_{uuid.uuid4()}"
    root.mkdir(parents=True)
    yield root
    shutil.rmtree(root, onerror=on_rm_error)


def _git_repo_with_origin(merge_root, name):
    path = merge_root / "namespace" / name
    path.mkdir(parents=True)
    repo = GitRepository(path=path)
    repo.init_repo()
    repo.commit_empty("Initial commit")

    origin_path = merge_root / "origin" / "namespace" / name
    origin = GitRepository(path=origin_path)
    origin.clone_from_disk(repo.path, is_bare=True)
    repo.urls = [str(origin_path)]
    repo._git("remote add origin {}", str(origin_path))
    repo.push(repo.default_branch, set_upstream=True)
    return repo


@pytest.fixture
def target1_repo(merge_root):
    return _git_repo_with_origin(merge_root, "target1")


@pytest.fixture
def target2_repo(merge_root):
    return _git_repo_with_origin(merge_root, "target2")


@pytest.fixture
def merge_auth_repo(
    merge_root, target1_repo, target2_repo, keystore_delegations, pin_manager
):
    """An authentication repository with two non-delegated target repositories."""
    auth_path = merge_root / "auth"
    auth_path.mkdir(parents=True)

    create_repository(
        str(auth_path),
        pin_manager,
        roles_key_infos=str(NO_YUBIKEYS_INPUT),
        keystore=keystore_delegations,
        commit=True,
        test=True,
    )
    auth_repo = AuthenticationRepository(path=auth_path, pin_manager=pin_manager)

    targets_dir = auth_path / "targets"
    (targets_dir / "repositories.json").write_text(
        json.dumps(
            {
                "repositories": {
                    "namespace/target1": {"custom": {"type": "targets"}},
                    "namespace/target2": {"custom": {"type": "targets"}},
                }
            }
        )
    )
    (targets_dir / "mirrors.json").write_text(
        json.dumps({"mirrors": ["https://github.com/{org_name}/{repo_name}.git"]})
    )
    (targets_dir / "namespace").mkdir(parents=True)
    for name, repo in (("target1", target1_repo), ("target2", target2_repo)):
        (targets_dir / "namespace" / name).write_text(
            json.dumps(
                {"branch": repo.default_branch, "commit": repo.head_commit().value}
            )
        )
    register_target_files(
        path=auth_path,
        pin_manager=pin_manager,
        keystore=keystore_delegations,
        commit=True,
        push=False,
        auth_repo=auth_repo,
    )
    return auth_repo
