from pathlib import Path
from typing import Optional
from taf.auth_repo import AuthenticationRepository
from taf.git import GitRepository


def check_target_file(
    target_repo_path: Path,
    target_repo_name: str,
    auth_repo: AuthenticationRepository,
    auth_repo_head_sha: Optional[str] = None,
):
    if auth_repo_head_sha is None:
        auth_repo_head_sha = auth_repo.head_commit_sha()
    target_repo = GitRepository(path=target_repo_path)
    target_repo_head_sha = target_repo.head_commit_sha()
    targets = auth_repo.targets_at_revisions(auth_repo_head_sha)
    target_content = targets[auth_repo_head_sha][target_repo_name]
    branch = target_repo.default_branch
    return (
        target_repo_head_sha == target_content["commit"]
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
