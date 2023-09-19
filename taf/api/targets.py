from logging import DEBUG, ERROR, INFO
from typing import Dict, List, Optional
import click
import os
import json
from collections import defaultdict
from pathlib import Path
from logdecorator import log_on_end, log_on_error, log_on_start
from taf.api.metadata import update_snapshot_and_timestamp, update_target_metadata
from taf.api.roles import (
    _initialize_roles_and_keystore,
    add_role,
    add_role_paths,
    remove_paths,
)
from taf.api.utils import check_if_clean, commit_and_push
from taf.constants import DEFAULT_RSA_SIGNATURE_SCHEME
from taf.exceptions import TAFError
from taf.git import GitRepository

import taf.repositoriesdb as repositoriesdb
from taf.log import taf_logger
from taf.auth_repo import AuthenticationRepository
from taf.repository_tool import Repository
from tuf.repository_tool import TARGETS_DIRECTORY_NAME


@log_on_start(DEBUG, "Adding target repository {target_name:s}", logger=taf_logger)
@log_on_end(DEBUG, "Finished adding target repository", logger=taf_logger)
@log_on_error(
    ERROR,
    "An error occurred while adding a new target repository {target_name:s}: {e}",
    logger=taf_logger,
    on_exceptions=TAFError,
    reraise=True,
)
@check_if_clean
def add_target_repo(
    path: str,
    target_path: str,
    target_name: str,
    role: str,
    library_dir: str,
    keystore: str,
    scheme: Optional[str] = DEFAULT_RSA_SIGNATURE_SCHEME,
    custom: Optional[Dict] = None,
    commit: Optional[bool] = True,
    prompt_for_keys: Optional[bool] = False,
) -> None:
    """
    Add a new target repository by adding it to repositories.json, creating a delegation (if targets is not
    its signing role) and adding and signing initial target files if the repository already exists on the filesystem.
    Also saves custom information about the repositories to repositories.json if it is provided.

    Arguments:
        path: Path to the authentication repository.
        target_path: Path to the target repository which is to be added.
        target_name (optional): Target repository's name. If not provided, it is determined based on the target path (the last two directories).
        role: Name of the role which will be responsible for signing the new target file.
        library_dir (optional): Path to the library's root directory. Determined based on the authentication repository's path if not provided.
        threshold: Signature's threshold.
        keystore: Location of the keystore files.
        scheme (optional): Signing scheme. Set to rsa-pkcs1v15-sha256 by default.
        custom (optional): Additional data that will be added to repositories.json if specified.
        commit (optional): Indicates if the changes should be committed and pushed automatically.
        prompt_for_keys (optional): Whether to ask the user to enter their key if it is not located inside the keystore directory.

    Side Effects:
        Updates metadata and repositories.json, adds a new target file if repository exists and writes changes to disk
        and commits changes.

    Raises:
        TAFError if the dependency cannot be instantiated or the default branch cannot be determined
    Returns:
        None
    """
    auth_repo = AuthenticationRepository(path=path)
    if not auth_repo.is_git_repository_root:
        print(f"{path} is not a git repository!")
        return
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
        parent_role = input("Enter new role's parent role (targets): ")
        paths = input(
            "Enter a comma separated list of path delegated to the new role: "
        )
        paths = [path.strip() for path in paths.split(",") if len(path.strip())]
        keys_number = input("Enter the number of signing keys of the new role (1): ")
        keys_number = int(keys_number or 1)
        threshold = input("Enter signatures threshold of the new role (1): ")
        threshold = int(threshold or 1)
        yubikey = click.confirm("Sign the new role's metadata using yubikeys? ")
        if target_name not in paths:
            paths.append(target_name)

        add_role(
            path=path,
            role=role,
            parent_role=parent_role or "targets",
            paths=paths,
            keys_number=keys_number,
            threshold=threshold,
            yubikey=yubikey,
            keystore=keystore,
            scheme=DEFAULT_RSA_SIGNATURE_SCHEME,
            commit=False,
            auth_repo=auth_repo,
            prompt_for_keys=prompt_for_keys,
        )
    else:
        print("Role already exists")
        add_role_paths(
            paths=[target_name],
            delegated_role=role,
            keystore=keystore,
            commit=False,
            auth_repo=auth_repo,
            prompt_for_keys=prompt_for_keys,
        )

    # target repo should be added to repositories.json
    # delegation paths should be extended if role != targets
    # if the repository already exists, create a target file
    repositories_json = repositoriesdb.load_repositories_json(auth_repo)
    repositories = repositories_json["repositories"]
    if target_repo.name in repositories:
        print(f"{target_repo.name} already added to repositories.json. Overwriting")
    repositories[target_repo.name] = {}
    if custom:
        repositories[target_name]["custom"] = custom

    # update content of repositories.json before updating targets metadata
    Path(auth_repo.path, repositoriesdb.REPOSITORIES_JSON_PATH).write_text(
        json.dumps(repositories_json, indent=4)
    )

    added_targets_data = {}
    if target_repo.is_git_repository_root:
        _save_top_commit_of_repo_to_target(
            library_dir, target_repo.name, auth_repo.path
        )
        added_targets_data[target_repo.name] = {}

    removed_targets_data = {}
    added_targets_data[repositoriesdb.REPOSITORIES_JSON_NAME] = {}
    update_target_metadata(
        auth_repo,
        added_targets_data,
        removed_targets_data,
        keystore,
        write=False,
        scheme=scheme,
        prompt_for_keys=prompt_for_keys,
    )

    # update snapshot and timestamp calls write_all, so targets updates will be saved too
    update_snapshot_and_timestamp(
        auth_repo, keystore, scheme=scheme, prompt_for_keys=prompt_for_keys
    )
    if commit:
        commit_and_push(auth_repo)
    else:
        print("\nPlease commit manually\n")


def export_targets_history(
    path: str,
    commit: Optional[bool] = None,
    output: Optional[str] = None,
    target_repos: Optional[List[str]] = None,
) -> None:
    """
    Form a dictionary consisting of branches and commits belonging to it for every target repository
    and either save it to a file or write to console.

    Arguments:
        path: Path to the authentication repository.
        commit (optional): Authentication repository's commit which marks the first commit for which the data should be generated.
        output (optional): File to which the exported history should be written.
        target_repos (optional): A list of target repository names whose history should be generated. All target repositories
        will be included if not provided.

    Side Effects:
       None

    Returns:
        None
    """
    auth_repo = AuthenticationRepository(path=path)
    commits = auth_repo.all_commits_since_commit(commit, auth_repo.default_branch)
    if not len(target_repos):
        target_repos = None
    else:
        repositoriesdb.load_repositories(auth_repo)
        invalid_targets = []
        for target_repo in target_repos:
            if repositoriesdb.get_repository(auth_repo, target_repo) is None:
                invalid_targets.append(target_repo)
        if len(invalid_targets):
            print(
                f"The following target repositories are not defined: {', '.join(invalid_targets)}"
            )
            return

    commits_on_branches = auth_repo.sorted_commits_and_branches_per_repositories(
        commits, target_repos
    )
    commits_json = json.dumps(commits_on_branches, indent=4)
    if output is not None:
        output = Path(output).resolve()
        if output.suffix != ".json":
            output = output.with_suffix(".json")
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(commits_json)
        print(f"Result written to {output}")
    else:
        print(commits_json)


def list_targets(
    path: str,
    library_dir: Optional[str] = None,
) -> None:
    """
    Prints a list of target repositories of an authentication repository and their states (are the work directories clean, are there
    remove changes that have not yed been pulled, are there commits that have not yet been signed).

    Arguments:
        path: Authentication repository's location
        library_dir (optional): Path to the library's root directory. Determined based on the authentication repository's path if not provided.

    Side Effects:
       None

    Returns:
        None
    """
    path = Path(path).resolve()
    auth_repo = AuthenticationRepository(path=path)
    top_commit = [auth_repo.head_commit_sha()]
    if library_dir is None:
        library_dir = path.parent.parent
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
            repo_output["something-to-commit"] = repo.something_to_commit()

    print(json.dumps(output, indent=4))


@log_on_start(INFO, "Signing target files", logger=taf_logger)
@log_on_error(
    ERROR,
    "An error occurred while signing target files: {e}",
    logger=taf_logger,
    on_exceptions=TAFError,
    reraise=True,
)
def register_target_files(
    path,
    keystore: Optional[str] = None,
    roles_key_infos: Optional[str] = None,
    commit: Optional[bool] = True,
    scheme: Optional[str] = DEFAULT_RSA_SIGNATURE_SCHEME,
    taf_repo: Optional[Repository] = None,
    write: Optional[bool] = False,
    prompt_for_keys: Optional[bool] = False,
):
    """
    Register all files found in the target directory as targets - update the targets
    metadata file, snapshot and timestamp and sign them. Commit changes if commit is set to True.

    Arguments:
        path: Authentication repository's path.
        keystore: Location of the keystore files.
        roles_key_infos: A dictionary whose keys are role names, while values contain information about the keys.
        scheme (optional): Signing scheme. Set to rsa-pkcs1v15-sha256 by default.
        taf_repo (optional): If taf repository is already initialized, it can be passed and used.
        write (optional): Write metadata updates to disk if set to True
        commit (optional): Indicates if the changes should be committed and pushed automatically.
        prompt_for_keys (optional): Whether to ask the user to enter their key if it is not located inside the keystore directory.

    Side Effects:
       Updates metadata files, writes changes to disk and optionally commits changes.

    Returns:
        True if there were targets that were updated, False otherwise
    """
    roles_key_infos, keystore = _initialize_roles_and_keystore(
        roles_key_infos, keystore, enter_info=False
    )
    if taf_repo is None:
        path = Path(path).resolve()
        taf_repo = Repository(str(path))

    # find files that should be added/modified/removed
    added_targets_data, removed_targets_data = taf_repo.get_all_target_files_state()
    # TODO
    updated = update_target_metadata(
        taf_repo,
        added_targets_data,
        removed_targets_data,
        keystore,
        scheme=scheme,
        write=write,
        prompt_for_keys=prompt_for_keys,
    )

    if write:
        taf_repo.writeall()
        if commit:
            auth_repo = GitRepository(path=taf_repo.path)
            commit_and_push(auth_repo)
        else:
            print("\nPlease commit manually\n")

    return updated


@log_on_start(DEBUG, "Removing target repository {target_name:s}", logger=taf_logger)
@log_on_end(DEBUG, "Finished removing target repository", logger=taf_logger)
@log_on_error(
    ERROR,
    "An error occurred while removing target repository {target_name:s}: {e}",
    logger=taf_logger,
    on_exceptions=TAFError,
    reraise=True,
)
@check_if_clean
def remove_target_repo(
    path: str, target_name: str, keystore: str, prompt_for_keys: Optional[bool] = False
) -> None:
    """
    Remove target repository from repositories.json, remove delegation, and target files and
    commit changes.

    Arguments:
        path: Authentication repository's path.
        target_name: Name of the target name which is to be removed.
        keystore: Location of the keystore files.
        prompt_for_keys (optional): Whether to ask the user to enter their key if it is not located inside the keystore directory.

    Side Effects:
       Updates metadata files, writes changes to disk and optionally commits changes.

    Returns:
        None
    """
    auth_repo = AuthenticationRepository(path=path)
    removed_targets_data = {}
    added_targets_data = {}
    if not auth_repo.is_git_repository_root:
        taf_logger.info(f"{path} is not a git repository!")
        return
    repositories_json = repositoriesdb.load_repositories_json(auth_repo)
    repositories = repositories_json["repositories"]
    if target_name not in repositories:
        taf_logger.info(f"{target_name} not in repositories.json")
    else:
        repositories.pop(target_name)
        # update content of repositories.json before updating targets metadata
        Path(auth_repo.path, repositoriesdb.REPOSITORIES_JSON_PATH).write_text(
            json.dumps(repositories_json, indent=4)
        )
        added_targets_data[repositoriesdb.REPOSITORIES_JSON_NAME] = {}

    auth_repo_targets_dir = Path(auth_repo.path, TARGETS_DIRECTORY_NAME)
    target_file_path = auth_repo_targets_dir / target_name

    if target_file_path.is_file():
        os.unlink(str(target_file_path))
        removed_targets_data[target_name] = {}
    else:
        taf_logger.info(f"{target_file_path} target file does not exist")

    changes_committed = False
    if len(added_targets_data) or len(removed_targets_data):
        update_target_metadata(
            auth_repo,
            added_targets_data,
            removed_targets_data,
            keystore,
            write=False,
            prompt_for_keys=prompt_for_keys,
        )

        update_snapshot_and_timestamp(
            auth_repo,
            keystore,
            scheme=DEFAULT_RSA_SIGNATURE_SCHEME,
            prompt_for_keys=prompt_for_keys,
        )
        auth_repo.commit(f"Remove {target_name} target")
        changes_committed = True

    delegation_existed = remove_paths(
        path, [target_name], keystore, commit=False, prompt_for_keys=prompt_for_keys
    )
    if delegation_existed:
        update_snapshot_and_timestamp(
            auth_repo,
            keystore,
            scheme=DEFAULT_RSA_SIGNATURE_SCHEME,
            prompt_for_keys=prompt_for_keys,
        )
        auth_repo.commit(f"Remove {target_name} from delegated paths")
        changes_committed = True
    else:
        taf_logger.info(f"{target_name} not among delegated paths")
    # update snapshot and timestamp calls write_all, so targets updates will be saved too
    if changes_committed:
        auth_repo.push()


def _save_top_commit_of_repo_to_target(
    library_dir: Path,
    repo_name: str,
    auth_repo_path: Path,
    add_branch: Optional[bool] = True,
) -> None:
    """
    Determine the top commit of a target repository and write it to the corresponding
    target file.
    """
    auth_repo_targets_dir = auth_repo_path / TARGETS_DIRECTORY_NAME
    target_repo_path = library_dir / repo_name
    namespace_and_name = repo_name.rsplit("/", 1)
    targets_dir = auth_repo_targets_dir
    if len(namespace_and_name) > 1:
        namespace, _ = namespace_and_name
        targets_dir = auth_repo_targets_dir / namespace
    targets_dir.mkdir(parents=True, exist_ok=True)
    _update_target_repos(auth_repo_path, targets_dir, target_repo_path, add_branch)


@log_on_start(DEBUG, "Updating target files", logger=taf_logger)
@log_on_end(DEBUG, "Finished updating target files", logger=taf_logger)
@log_on_error(
    ERROR,
    "An error occurred while updating target files: {e}",
    logger=taf_logger,
    on_exceptions=TAFError,
    reraise=True,
)
@check_if_clean
def update_target_repos_from_repositories_json(
    path: str,
    library_dir: str,
    keystore: str,
    add_branch: Optional[bool] = True,
    scheme: Optional[str] = DEFAULT_RSA_SIGNATURE_SCHEME,
    commit: Optional[bool] = True,
    prompt_for_keys: Optional[bool] = False,
) -> None:
    """
    Create or update target files by reading the latest commit's repositories.json

    Arguments:
        path: Authentication repository's location.
        library_dir: Path to the library's root directory. Determined based on the authentication repository's path if not provided.
        keystore: Location of the keystore files.
        add_branch: Indicates whether to add the current branch's name to the target file.
        scheme (optional): Signing scheme. Set to rsa-pkcs1v15-sha256 by default.
        commit (optional): Indicates if the changes should be committed and pushed automatically.
        prompt_for_keys (optional): Whether to ask the user to enter their key if it is not located inside the keystore directory.

    Side Effects:
       Update target and metadata files and writes changes to disk.

    Returns:
        None
    """
    path = Path(path).resolve()
    if library_dir is None:
        library_dir = path.parent.parent
    else:
        library_dir = Path(library_dir)
    auth_repo_targets_dir = path / TARGETS_DIRECTORY_NAME
    repositories_json = json.loads(
        Path(auth_repo_targets_dir / "repositories.json").read_text()
    )
    for repo_name in repositories_json.get("repositories"):
        _save_top_commit_of_repo_to_target(library_dir, repo_name, path, add_branch)
    register_target_files(
        path,
        keystore,
        None,
        commit,
        scheme,
        write=True,
        prompt_for_keys=prompt_for_keys,
    )


@log_on_start(DEBUG, "Updating target files", logger=taf_logger)
@log_on_end(DEBUG, "Finished updating target files", logger=taf_logger)
@log_on_error(
    ERROR,
    "An error occurred while updating target files: {e}",
    logger=taf_logger,
    on_exceptions=TAFError,
    reraise=True,
)
@check_if_clean
def update_and_sign_targets(
    path: str,
    library_dir: str,
    target_types: list,
    keystore: str,
    roles_key_infos: str,
    scheme: str,
    commit: Optional[bool] = True,
    prompt_for_keys: Optional[bool] = False,
) -> None:
    """
    Save the top commit of specified target repositories to the corresponding target files and sign.

    Arguments:
        path: Authentication repository's location.
        library_dir (optional): Path to the library's root directory. Determined based on the authentication repository's path if not provided.
        target_types: Types of target repositories whose corresponding target files should be updated and signed.
        keystore: Location of the keystore files.
        roles_key_infos: A dictionary whose keys are role names, while values contain information about the keys.
        scheme (optional): Signing scheme. Set to rsa-pkcs1v15-sha256 by default.
        commit (optional): Indicates if the changes should be committed and pushed automatically.
        prompt_for_keys (optional): Whether to ask the user to enter their key if it is not located inside the keystore directory.

    Side Effects:
       Update target and metadata files and writes changes to disk.

    Returns:
        None
    """
    path = Path(path).resolve()
    auth_repo = AuthenticationRepository(path=path)
    if library_dir is None:
        library_dir = path.parent.parent
    repositoriesdb.load_repositories(auth_repo)
    nonexistent_target_types = []
    target_names = []
    for target_type in target_types:
        try:
            target_name = repositoriesdb.get_repositories_paths_by_custom_data(
                auth_repo, type=target_type
            )[0]
            target_names.append(target_name)
        except Exception:
            nonexistent_target_types.append(target_type)
            continue
    if len(nonexistent_target_types):
        print(
            f"Target types {'.'.join(nonexistent_target_types)} not in repositories.json. Targets not updated"
        )
        return

    # only update target files if all specified types are valid
    for target_name in target_names:
        _save_top_commit_of_repo_to_target(library_dir, target_name, path, True)
        print(f"Updated {target_name} target file")
    register_target_files(
        path,
        keystore,
        roles_key_infos,
        commit,
        scheme,
        write=True,
        prompt_for_keys=prompt_for_keys,
    )


def _update_target_repos(
    repo_path: Path, targets_dir: Path, target_repo_path: Path, add_branch: bool
) -> None:
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
