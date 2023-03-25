from collections import defaultdict
import json
import os
from pathlib import Path
from taf.api.metadata import update_snapshot_and_timestamp
from taf.api.roles import add_role, add_role_paths, remove_paths
from taf.constants import DEFAULT_RSA_SIGNATURE_SCHEME
from taf.exceptions import TAFError
from taf.git import GitRepository
from taf.hosts import REPOSITORIES_JSON_PATH

import taf.repositoriesdb as repositoriesdb
from taf.auth_repo import AuthenticationRepository
from tuf.repository_tool import TARGETS_DIRECTORY_NAME


def add_target_repo(
    auth_path: str,
    target_path: str,
    target_name: str,
    role: str,
    library_dir: str,
    keystore: str,
    custom,
):
    auth_repo = AuthenticationRepository(path=auth_path)
    if library_dir is None:
        library_dir = auth_repo.path.parent.parent

    if target_name is not None:
        target_repo = GitRepository(library_dir, target_name)
    elif target_path is not None:
        target_repo = GitRepository(path=target_path)
    else:
        raise TAFError(
            "Cannot add new target repository. Specify either target name (and library dir) or target path"
        )

    existing_roles = auth_repo.get_all_targets_roles()
    if role not in existing_roles:
        parent_role = input("Enter new role's parent role: ")
        paths = input(
            "Enter a comma separated list of path delegated to the new role: "
        )
        paths = paths.split(",")
        keys_number = input("Enter the number of signing keys of the new role: ")
        keys_number = int(keys_number)
        threshold = input("Enter signatures threshold of the new role: ")
        threshold = int(threshold)
        yubikey = input(
            "Should the new role's metadata be signed using yubikeys? [y/n]: "
        )
        yubikey = yubikey == "y"
        add_role(
            auth_path,
            role,
            parent_role,
            paths,
            keys_number,
            threshold,
            yubikey,
            keystore,
            DEFAULT_RSA_SIGNATURE_SCHEME,
            commit=False,
        )

    # target repo should be added to repositories.json
    # delegation paths should be extended if role != targets
    # if the repository already exists, create a target file
    repositories_json = repositoriesdb.load_repositories_json(auth_repo)
    if target_repo.name in repositories_json:
        print(f"{target_repo.name} already added to repositories.json. Overwriting")
    repositories_json[target_repo.name] = {}
    if custom:
        repositories_json[target_name]["custom"] = custom

    if role != "targets":
        add_role_paths(
            [target_repo.name], role, keystore, commit=False, auth_repo=auth_repo
        )

    # update content of repositories.json before updating targets metadata
    Path(auth_repo.path, REPOSITORIES_JSON_PATH).write_text(
        json.dumps(repositories_json, indent=4)
    )

    if target_repo.is_git_repository_root:
        _save_top_commit_of_repo_to_target(
            library_dir, target_repo.name, auth_repo.path
        )

    # update snapshot and timestamp calls write_all, so targets updates will be saved too
    update_snapshot_and_timestamp(
        auth_repo, keystore, None, scheme=DEFAULT_RSA_SIGNATURE_SCHEME
    )
    commit_message = input("\nEnter commit message and press ENTER\n\n")
    auth_repo.commit(commit_message)


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


def remove_target_repo(
    auth_path: str,
    target_name: str,
    keystore: str,
):
    auth_repo = AuthenticationRepository(path=auth_path)
    repositories_json = repositoriesdb.load_repositories_json(auth_repo)
    repositories = repositories_json["repositories"]
    if target_name not in repositories:
        print(f"{target_name} not in repositories.json")
    else:
        repositories.pop(target_name)
        # update content of repositories.json before updating targets metadata
        Path(auth_repo.path, REPOSITORIES_JSON_PATH).write_text(
            json.dumps(repositories_json, indent=4)
        )

    remove_paths([target_name], keystore, commit=False, auth_repo=auth_repo)
    remove_target_file(target_name, auth_path)
    # update snapshot and timestamp calls write_all, so targets updates will be saved too
    update_snapshot_and_timestamp(
        auth_repo, keystore, None, scheme=DEFAULT_RSA_SIGNATURE_SCHEME
    )
    commit_message = input("\nEnter commit message and press ENTER\n\n")
    auth_repo.commit(commit_message)


def remove_target_file(repo_name: str, auth_repo_path: str):
    auth_repo_targets_dir = Path(auth_repo_path, TARGETS_DIRECTORY_NAME)
    target_file_path = auth_repo_targets_dir / repo_name
    if target_file_path.is_file():
        os.unlink(str(target_file_path))
    else:
        print(f"{target_file_path} target file does not exist")


def _save_top_commit_of_repo_to_target(
    library_dir: Path, repo_name: str, auth_repo_path: Path, add_branch: bool = True
):
    auth_repo_targets_dir = auth_repo_path / TARGETS_DIRECTORY_NAME
    target_repo_path = library_dir / repo_name
    namespace_and_name = repo_name.rsplit("/", 1)
    targets_dir = auth_repo_targets_dir
    if len(namespace_and_name) > 1:
        namespace, _ = namespace_and_name
        targets_dir = auth_repo_targets_dir / namespace
    targets_dir.mkdir(parents=True, exist_ok=True)
    _update_target_repos(auth_repo_path, targets_dir, target_repo_path, add_branch)


def _update_target_repos(repo_path, targets_dir, target_repo_path, add_branch):
    """Updates target repo's commit sha and branch"""
    if not target_repo_path.is_dir() or target_repo_path == repo_path:
        return
    target_repo = GitRepository(path=target_repo_path)
    if target_repo.is_git_repository:
        data = {"commit": target_repo.head_commit_sha()}
        if add_branch:
            data["branch"] = target_repo.get_current_branch()
        target_repo_name = target_repo_path.name
        path = targets_dir / target_repo_name
        path.write_text(json.dumps(data, indent=4))
        print(f"Updated {path}")
