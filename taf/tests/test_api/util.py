from pathlib import Path
from typing import Optional
from taf.auth_repo import AuthenticationRepository
from taf.git import GitRepository
from typing import List
import taf.repositoriesdb as repositoriesdb

from taf.models.types import Commitish


def check_target_file(
    target_repo_path: Path,
    target_repo_name: str,
    auth_repo: AuthenticationRepository,
    auth_repo_head_sha: Optional[Commitish] = None,
):
    if auth_repo_head_sha is None:
        auth_repo_head_sha = auth_repo.head_commit()
    target_repo = GitRepository(path=target_repo_path)
    target_repo_head_sha = target_repo.head_commit()
    assert target_repo_head_sha
    repositoriesdb.load_repositories(auth_repo)
    target_repos = {
        target_repo_name: repositoriesdb.get_repository(auth_repo, target_repo_name)
    }
    targets = auth_repo.targets_at_revisions(
        commits=[auth_repo_head_sha], target_repos=target_repos
    )
    target_content = targets[auth_repo_head_sha][target_repo_name]
    branch = target_repo.default_branch
    return (
        target_repo_head_sha.value == target_content["commit"]
        and branch == target_content["branch"]
    )


def check_if_targets_signed(
    auth_repo: AuthenticationRepository,
    signing_role: str,
    *targets_filenames,
):
    target_files = auth_repo.all_target_files()
    signed_target_files = auth_repo.get_signed_target_files()
    for target_file in targets_filenames:
        assert target_file in target_files
        assert target_file in signed_target_files
        assert auth_repo.get_role_from_target_paths([target_file]) == signing_role


def check_if_targets_removed(
    auth_repo: AuthenticationRepository,
    *targets_filenames,
):
    target_files = auth_repo.all_target_files()
    signed_target_files = auth_repo.get_signed_target_files()
    for target_file in targets_filenames:
        assert target_file not in target_files
        assert target_file not in signed_target_files


def check_new_role(
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
