from collections import defaultdict
from taf.updater.types.update import UpdateType
from taf.tests.test_updater.update_utils import (
    check_if_commits_match,
    check_last_validated_commit,
    clone_repositories,
)


def test_update_repository_with_dependencies(
    library_with_dependencies,
    origin_dir,
    client_dir,
):
    _clone_full_library(
        library_with_dependencies,
        origin_dir,
        client_dir,
        expected_repo_type=UpdateType.EITHER,
        excluded_target_globs=None,
    )


def _clone_full_library(
    library_dict,
    origin_dir,
    client_dir,
    expected_repo_type=UpdateType.EITHER,
    excluded_target_globs=None,
):

    all_repositories = []
    for repo_info in library_dict.values():
        # Add the auth repository
        all_repositories.append(repo_info["auth_repo"])
        # Extend the list with all target repositories
        all_repositories.extend(repo_info["target_repos"])

    start_head_shas = defaultdict(dict)
    for repo in all_repositories:
        for branch in repo.branches():
            start_head_shas[repo.name][branch] = repo.top_commit_of_branch(branch)

    origin_root_repo = library_dict["root/auth"]["auth_repo"]

    clone_repositories(
        origin_root_repo,
        client_dir,
        expected_repo_type=expected_repo_type,
    )

    repositories = {}
    for auth_repo_name, repos in library_dict.items():
        repositories[auth_repo_name] = repos["auth_repo"]
        for target_repo in repos["target_repos"]:
            repositories[target_repo.name] = target_repo
        check_last_validated_commit(client_dir / repos["auth_repo"].name)
    check_if_commits_match(
        repositories, origin_dir, start_head_shas, excluded_target_globs
    )
