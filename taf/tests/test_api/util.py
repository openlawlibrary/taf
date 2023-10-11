import json
from pathlib import Path
import shutil
from typing import Dict, Optional
from taf.auth_repo import AuthenticationRepository
from taf.git import GitRepository
from tuf.repository_tool import TARGETS_DIRECTORY_NAME


def copy_repositories_json(
    repositories_json_template: Dict, namespace: str, auth_repo_path: Path
):
    output = auth_repo_path / TARGETS_DIRECTORY_NAME

    repositories = {
        "repositories": {
            repo_name.format(namespace=namespace): repo_data
            for repo_name, repo_data in repositories_json_template[
                "repositories"
            ].items()
        }
    }
    output.mkdir(parents=True, exist_ok=True)
    Path(output / "repositories.json").write_text(json.dumps(repositories))


def copy_mirrors_json(mirrors_json_path: Path, auth_repo_path: Path):
    output = auth_repo_path / TARGETS_DIRECTORY_NAME
    shutil.copy(str(mirrors_json_path), output)


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
