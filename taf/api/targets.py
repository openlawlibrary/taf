from collections import defaultdict
import json
from pathlib import Path

import taf.repositoriesdb as repositoriesdb
from taf.auth_repo import AuthenticationRepository


# data: up to date with remote, uncommitted targets,
# unsigned targets, which targets are cloned/not
# cloned locally, bare/normal; display in pretty tree
# with optional json output, list dependencies


def list_targets(
    repo_path: str,
    library_dir: str,
):
    """
    <Purpose>
        Save the top commit of specified target repositories to the corresponding target files and sign
    <Arguments>
        repo_path:
        Authentication repository's location
        library_dir:
        Directory where target repositories and, optionally, authentication repository are locate
    """
    auth_path = Path(repo_path).resolve()
    auth_repo = AuthenticationRepository(path=auth_path)
    top_commit = [auth_repo.head_commit_sha()]
    if library_dir is None:
        library_dir = auth_path.parent.parent
    repositoriesdb.load_repositories(auth_repo)
    target_repositories = repositoriesdb.get_deduplicated_repositories(auth_repo)
    repositories_data = auth_repo.sorted_commits_and_branches_per_repositories(
        top_commit
    )
    output = defaultdict(dict)
    for repo_name, repo_data in repositories_data.items():
        repo = target_repositories[repo_name]
        local_repo_exists = repo.is_git_repository_root
        repo_output = {}
        output[repo_name] = repo_output
        repo_output["unauthenticated-allowed"] = repo.custom.get(
            "allow-unauthenticated-commits", False
        )
        repo_output["cloned"] = local_repo_exists
        if local_repo_exists:
            repo_output["bare"] = repo.is_bare_repository()
            # there will only be one branch since only data corresponding to the top auth commit was loaded
            for branch, branch_data in repo_data.items():
                branch_data = branch_data[0]
                repo_output["unsigned"] = False
                if not repo.branch_exists(branch, include_remotes=False):
                    repo_output["up-to-date"] = False
                else:
                    is_synced_with_remote = repo.synced_with_remote(branch=branch)
                    repo_output["up-to-date"] = is_synced_with_remote
                    if not is_synced_with_remote:
                        last_signed_commit = branch_data["commit"]
                        if branch in repo.branches_containing_commit(
                            last_signed_commit
                        ):
                            top_commit = repo.top_commit_of_branch(branch)
                            repo_output[
                                "unsigned"
                            ] = top_commit in repo.all_commits_since_commit(
                                last_signed_commit, branch
                            )
            repo_output["uncommitted"] = repo.something_to_commit()

    print(json.dumps(output, indent=4))


def add_repo(
    auth_path: str,
    target_path: str,
    role: str,
    library_dir: str,
    keystore: str,
):
    auth_repo = AuthenticationRepository(path=auth_path)
