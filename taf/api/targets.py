from logging import DEBUG, ERROR, INFO
from typing import Dict, List, Optional, Union
import os
import json
from collections import defaultdict
from pathlib import Path
from logdecorator import log_on_end, log_on_error, log_on_start
from taf.api.api_workflow import manage_repo_and_signers
from taf.api.roles import (
    initialize_roles_and_keystore,
    add_role,
    add_role_paths,
    remove_paths,
)
from taf.api.utils._conf import read_keys_name_mapping
from taf.api.utils._git import check_if_clean_and_synced
from taf.constants import DEFAULT_RSA_SIGNATURE_SCHEME, TARGETS_DIRECTORY_NAME
from taf.exceptions import TAFError
from taf.git import GitRepository
from taf.messages import git_commit_message

from taf.models.types import Commitish
import taf.repositoriesdb as repositoriesdb
from taf.log import taf_logger
from taf.auth_repo import AuthenticationRepository
from taf.yubikey.yubikey_manager import PinManager


@check_if_clean_and_synced
@log_on_start(DEBUG, "Adding target repository {target_name:s}", logger=taf_logger)
@log_on_end(DEBUG, "Finished adding target repository", logger=taf_logger)
@log_on_error(
    ERROR,
    "An error occurred while adding a new target repository {target_name:s}: {e}",
    logger=taf_logger,
    on_exceptions=TAFError,
    reraise=True,
)
def add_target_repo(
    path: str,
    pin_manager: PinManager,
    target_path: str,
    target_name: str,
    role: str,
    library_dir: str,
    keystore: str,
    should_create_new_role: bool,
    parent_role: Optional[str] = None,
    paths: Optional[List] = None,
    keys_number: Optional[int] = None,
    threshold: Optional[int] = None,
    yubikey: Optional[bool] = None,
    scheme: Optional[str] = DEFAULT_RSA_SIGNATURE_SCHEME,
    custom: Optional[Dict] = None,
    commit: Optional[bool] = True,
    prompt_for_keys: Optional[bool] = False,
    push: Optional[bool] = True,
    keys_description: Optional[str] = None,
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
        push (optional): Flag specifying whether to push to remote

    Side Effects:
        Updates metadata and repositories.json, adds a new target file if repository exists and writes changes to disk
        and commits changes.

    Raises:
        TAFError if the dependency cannot be instantiated or the default branch cannot be determined
    Returns:
        None
    """
    auth_repo = AuthenticationRepository(path=path, pin_manager=pin_manager)
    keys_name_mappings = read_keys_name_mapping(keys_description)
    auth_repo.add_key_names(keys_name_mappings)

    if library_dir is None:
        library_dir = str(auth_repo.path.parent.parent)

    if target_path is not None:
        target_repo = GitRepository(path=target_path)
        target_name = target_repo.name
    elif target_name is None:
        raise TAFError(
            "Cannot add new target repository. Specify either target name or target path"
        )

    existing_roles = auth_repo.get_all_targets_roles()
    if role not in existing_roles:
        if not should_create_new_role:
            taf_logger.error(f"Role {role} does not exist")
            return
        else:
            taf_logger.log("NOTICE", f"Role {role} does not exist. Creating a new role")

            add_role(
                path=path,
                pin_manager=pin_manager,
                role=role,
                parent_role=parent_role or "targets",
                paths=paths,
                keys_number=keys_number,
                threshold=threshold,
                yubikey=yubikey,
                keystore=keystore,
                scheme=DEFAULT_RSA_SIGNATURE_SCHEME,
                commit=True,
                push=False,
                auth_repo=auth_repo,
                prompt_for_keys=prompt_for_keys,
            )
    elif role != "targets":
        # delegated role paths are not specified for the top-level targets role
        # the targets role is responsible for signing all paths not
        # delegated to another target role
        taf_logger.info("Role already exists")
        add_role_paths(
            path=auth_repo.path,
            paths=[target_name],
            pin_manager=pin_manager,
            delegated_role=role,
            keystore=keystore,
            commit=True,
            push=False,
            auth_repo=auth_repo,
            prompt_for_keys=prompt_for_keys,
        )

    _add_target_repository_to_repositories_json(auth_repo, target_name, custom)
    commit_msg = git_commit_message("add-target", target_name=target_name)
    register_target_files(
        path=path,
        pin_manager=pin_manager,
        keystore=keystore,
        commit=commit,
        scheme=scheme,
        auth_repo=auth_repo,
        update_snapshot_and_timestamp=True,
        prompt_for_keys=prompt_for_keys,
        push=push,
        no_commit_warning=True,
        reset_updated_targets_on_error=True,
        commit_msg=commit_msg,
    )


# TODO Move this to auth repo when repositoriesdb is removed and there are no circular imports
def _add_target_repository_to_repositories_json(
    auth_repo, target_repo_name: str, custom: Optional[Dict] = None
) -> None:
    """
    Add repository to repositories.json
    """
    if custom is None:
        custom = {}
    # target repo should be added to repositories.json
    # delegation paths should be extended if role != targets
    # if the repository already exists, create a target file
    repositories_json = repositoriesdb.load_repositories_json(auth_repo)
    if repositories_json is None:
        repositories_json = {"repositories": {}}
    repositories = repositories_json["repositories"]
    if target_repo_name in repositories:
        auth_repo._log_notice(
            f"{target_repo_name} already added to repositories.json. Overwriting"
        )

    repositories[target_repo_name] = {}
    if custom:
        repositories[target_repo_name]["custom"] = custom

    # update content of repositories.json before updating targets metadata
    full_repositories_json_path = Path(
        auth_repo.path, repositoriesdb.REPOSITORIES_JSON_PATH
    )
    if not full_repositories_json_path.parent.is_dir():
        full_repositories_json_path.parent.mkdir()

    Path(auth_repo.path, repositoriesdb.REPOSITORIES_JSON_PATH).write_text(
        json.dumps(repositories_json, indent=4)
    )


def export_targets_history(
    path: str,
    commit: Optional[Commitish] = None,
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
    repositoriesdb.load_repositories(auth_repo)
    if target_repos:
        invalid_targets = []
        target_repositories = {}
        for target_repo in target_repos:
            repo = repositoriesdb.get_repository(auth_repo, target_repo)
            if repo is None:
                invalid_targets.append(target_repo)
            else:
                target_repositories[target_repo] = repo
        if len(invalid_targets):
            taf_logger.log(
                "NOTICE",
                f"The following target repositories are not defined: {', '.join(invalid_targets)}",
            )
            return
    else:
        target_repositories = repositoriesdb.get_deduplicated_repositories(auth_repo)

    commits_on_branches = auth_repo.sorted_commits_and_branches_per_repositories(
        commits, target_repositories
    )
    commits_json = json.dumps(commits_on_branches, indent=4)
    if output is not None:
        output_path = Path(output).resolve()
        if output_path.suffix != ".json":
            output_path = output_path.with_suffix(".json")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(commits_json)
        taf_logger.log("NOTICE", f"Result written to {output_path}")
    else:
        taf_logger.log("NOTICE", commits_json)


def list_targets(
    path: str,
) -> Dict:
    """
    Returns a dictionary containing target repositories of an authentication repository and their states (are the work directories clean, are there
    remove changes that have not yed been pulled, are there commits that have not yet been signed).

    Arguments:
        path: Authentication repository's location
        library_dir (optional): Path to the library's root directory. Determined based on the authentication repository's path if not provided.

    Side Effects:
       None

    Returns:
        None
    """
    auth_repo = AuthenticationRepository(path=path)
    head_commit = auth_repo.head_commit()
    if head_commit is None:
        taf_logger.log("NOTICE", "Repository is empty")
        return {}
    top_commit = [head_commit]
    repositoriesdb.load_repositories(auth_repo)
    target_repositories = repositoriesdb.get_deduplicated_repositories(auth_repo)
    repositories_data = auth_repo.sorted_commits_and_branches_per_repositories(
        top_commit, target_repositories
    )
    output: Dict = defaultdict(dict)
    for repo_name, repo_data in repositories_data.items():
        repo = target_repositories[repo_name]
        local_repo_exists = repo.is_git_repository_root
        repo_output: Dict = {}
        output[repo_name] = repo_output
        repo_output["unauthenticated-allowed"] = repo.custom.get(
            "allow-unauthenticated-commits", False
        )
        repo_output["cloned"] = local_repo_exists
        if local_repo_exists:
            repo_output["bare"] = repo.is_bare_repository
            repo_output["unsigned"] = []
            # there will only be one branch since only data corresponding to the top auth commit was loaded
            for branch, branch_data in repo_data.items():
                has_remote = repo.has_remote()
                repo_output["has-remote"] = has_remote

                if not repo.branch_exists(branch, include_remotes=False):
                    repo_output["up-to-date"] = False
                else:
                    if has_remote:
                        is_synced_with_remote = repo.synced_with_remote(branch=branch)
                        repo_output["up-to-date"] = is_synced_with_remote

                    last_signed_commit = branch_data[0]["commit"]
                    if branch in repo.branches_containing_commit(last_signed_commit):
                        branch_top_commit = repo.top_commit_of_branch(branch)
                        unsigned_commits = repo.all_commits_since_commit(
                            last_signed_commit, branch
                        )
                        if (
                            len(unsigned_commits)
                            and branch_top_commit in unsigned_commits
                        ):
                            repo_output["unsigned"].append(branch)
            repo_output["something-to-commit"] = repo.something_to_commit()

    return output


@log_on_start(INFO, "Signing target files", logger=taf_logger)
@log_on_error(
    ERROR,
    "An error occurred while signing target files: {e}",
    logger=taf_logger,
    on_exceptions=TAFError,
    reraise=True,
)
def register_target_files(
    path: Union[Path, str],
    pin_manager: PinManager,
    keystore: Optional[str] = None,
    roles_key_infos: Optional[str] = None,
    commit: Optional[bool] = True,
    scheme: Optional[str] = DEFAULT_RSA_SIGNATURE_SCHEME,
    auth_repo: Optional[AuthenticationRepository] = None,
    update_snapshot_and_timestamp: Optional[bool] = True,
    prompt_for_keys: Optional[bool] = False,
    push: Optional[bool] = True,
    no_commit_warning: Optional[bool] = True,
    reset_updated_targets_on_error: Optional[bool] = False,
    commit_msg: Optional[str] = None,
    force_update_of_roles: Optional[str] = None,
):
    """
    Register all files found in the target directory as targets - update the targets
    metadata file, snapshot and timestamp and sign them. Commit changes if commit is set to True.

    Arguments:
        path: Authentication repository's path.
        keystore: Location of the keystore files.
        roles_key_infos: A dictionary whose keys are role names, while values contain information about the keys.
        scheme (optional): Signing scheme. Set to rsa-pkcs1v15-sha256 by default.
        auth_repo (optional): If auth repository is already initialized, it can be passed and used.
        write (optional): Write metadata updates to disk if set to True
        commit (optional): Indicates if the changes should be committed and pushed automatically.
        prompt_for_keys (optional): Whether to ask the user to enter their key if it is not located inside the keystore directory.
        push (optional): Flag specifying whether to push to remote
        force_update_of_roles (optional): A list of roles whose version should be updated, even
        if no other changes are made
    Side Effects:
       Updates metadata files, writes changes to disk and optionally commits changes.

    Returns:
        True if there were targets that were updated, False otherwise
    """

    # find files that should be added/modified/removed

    if auth_repo is None:
        auth_repo = AuthenticationRepository(path=path, pin_manager=pin_manager)
    elif auth_repo.pin_manager is None:
        auth_repo.pin_manager = pin_manager

    keys_name_mappings = read_keys_name_mapping(roles_key_infos)
    auth_repo.add_key_names(keys_name_mappings)

    added_targets_data, removed_targets_data = auth_repo.get_all_target_files_state()
    if not added_targets_data and not removed_targets_data:
        taf_logger.log("NOTICE", "No added or removed targets")
        return False

    all_updated_targets = list(added_targets_data.keys()) if added_targets_data else []
    if removed_targets_data:
        all_updated_targets.extend(list(removed_targets_data.keys()))

    roles_and_targets = defaultdict(list)
    paths_to_reset: List = []
    for path in all_updated_targets:
        roles_and_targets[auth_repo.get_role_from_target_paths([path])].append(path)
        if reset_updated_targets_on_error:
            paths_to_reset.append(str(Path(TARGETS_DIRECTORY_NAME, path)))

    _, keystore, _ = initialize_roles_and_keystore(
        roles_key_infos, keystore, enter_info=False
    )

    roles_to_load = list(roles_and_targets.keys())
    if force_update_of_roles:
        for role in force_update_of_roles:
            if role not in roles_to_load:
                roles_to_load.append(role)
    with manage_repo_and_signers(
        auth_repo,
        roles_to_load,
        keystore,
        scheme,
        prompt_for_keys,
        load_snapshot_and_timestamp=update_snapshot_and_timestamp,
        load_parents=False,
        load_roles=True,
        commit=commit,
        push=push,
        commit_msg=commit_msg,
        commit_key="update-targets",
        no_commit_warning=no_commit_warning,
        paths_to_reset_on_error=paths_to_reset,
    ):
        for role, targets in roles_and_targets.items():
            auth_repo.update_target_role(role, targets)
        if force_update_of_roles:
            for role in force_update_of_roles:
                if role not in roles_and_targets:
                    auth_repo.update_target_role(role, None, True)

        if update_snapshot_and_timestamp:
            auth_repo.update_snapshot_and_timestamp()


@check_if_clean_and_synced
@log_on_start(DEBUG, "Removing target repository {target_name:s}", logger=taf_logger)
@log_on_end(DEBUG, "Finished removing target repository", logger=taf_logger)
@log_on_error(
    ERROR,
    "An error occurred while removing target repository {target_name:s}: {e}",
    logger=taf_logger,
    on_exceptions=TAFError,
    reraise=True,
)
def remove_target_repo(
    path: str,
    pin_manager: PinManager,
    target_name: str,
    keystore: str,
    prompt_for_keys: Optional[bool] = False,
    push: Optional[bool] = True,
    scheme: Optional[str] = DEFAULT_RSA_SIGNATURE_SCHEME,
    keys_description: Optional[str] = None,
) -> None:
    """
    Remove target repository from repositories.json, remove delegation, and target files and
    commit changes.

    Arguments:
        path: Authentication repository's path.
        target_name: Name of the target name which is to be removed.
        keystore: Location of the keystore files.
        prompt_for_keys (optional): Whether to ask the user to enter their key if it is not located inside the keystore directory.
        push (optional): Flag specifying whether to push to remote
    Side Effects:
       Updates metadata files, writes changes to disk and optionally commits changes.

    Returns:
        None
    """
    auth_repo = AuthenticationRepository(path=path, pin_manager=pin_manager)
    keys_name_mappings = read_keys_name_mapping(keys_description)
    auth_repo.add_key_names(keys_name_mappings)

    tarets_updated = _remove_from_repositories_json(auth_repo, target_name)

    auth_repo_targets_dir = auth_repo.path / TARGETS_DIRECTORY_NAME
    target_file_path = auth_repo_targets_dir / target_name

    if target_file_path.is_file():
        os.unlink(str(target_file_path))
        tarets_updated = True
    else:
        taf_logger.log("NOTICE", f"{target_file_path} target file does not exist")

    changes_committed = False
    if tarets_updated:
        commit_msg = git_commit_message("remove-target", target_name=target_name)
        register_target_files(
            path=path,
            pin_manager=pin_manager,
            keystore=keystore,
            commit=True,
            scheme=scheme,
            auth_repo=auth_repo,
            update_snapshot_and_timestamp=True,
            prompt_for_keys=prompt_for_keys,
            push=push,
            no_commit_warning=True,
            reset_updated_targets_on_error=True,
            commit_msg=commit_msg,
        )

        changes_committed = True

    commit_msg = git_commit_message(
        "remove-from-delegated-paths", target_name=target_name
    )
    delegation_existed = remove_paths(
        path,
        [target_name],
        keystore=keystore,
        commit=True,
        prompt_for_keys=prompt_for_keys,
        push=False,
        commit_msg=commit_msg,
    )
    if delegation_existed:
        changes_committed = True

    # update snapshot and timestamp calls write_all, so targets updates will be saved too
    if changes_committed and push:
        auth_repo.push()


def _remove_from_repositories_json(auth_repo, target_name):
    repositories_json = repositoriesdb.load_repositories_json(auth_repo)
    if repositories_json is not None:
        repositories = repositories_json["repositories"]
        if target_name not in repositories:
            taf_logger.log("NOTICE", f"{target_name} not in repositories.json")
            return False
        else:
            repositories.pop(target_name)
            # update content of repositories.json before updating targets metadata
            Path(auth_repo.path, repositoriesdb.REPOSITORIES_JSON_PATH).write_text(
                json.dumps(repositories_json, indent=4)
            )
            return True
    else:
        taf_logger.log("NOTICE", f"{target_name} not in repositories.json")
        return False


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


@check_if_clean_and_synced
@log_on_start(DEBUG, "Updating target files", logger=taf_logger)
@log_on_end(DEBUG, "Finished updating target files", logger=taf_logger)
@log_on_error(
    ERROR,
    "An error occurred while updating target files: {e}",
    logger=taf_logger,
    on_exceptions=TAFError,
    reraise=True,
)
def update_target_repos_from_repositories_json(
    path: str,
    pin_manager: PinManager,
    library_dir: str,
    keystore: str,
    add_branch: Optional[bool] = True,
    scheme: Optional[str] = DEFAULT_RSA_SIGNATURE_SCHEME,
    commit: Optional[bool] = True,
    prompt_for_keys: Optional[bool] = False,
    push: Optional[bool] = True,
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
        push (optional): Flag specifying whether to push to remote
    Side Effects:
       Update target and metadata files and writes changes to disk.

    Returns:
        None
    """
    repo_path = Path(path).resolve()
    if library_dir is None:
        library_dir = str(repo_path.parent.parent)

    auth_repo_targets_dir = repo_path / TARGETS_DIRECTORY_NAME
    repositories_json = json.loads(
        Path(auth_repo_targets_dir / "repositories.json").read_text()
    )
    for repo_name in repositories_json.get("repositories"):
        _save_top_commit_of_repo_to_target(
            Path(library_dir), repo_name, repo_path, add_branch
        )

    register_target_files(
        repo_path,
        pin_manager,
        keystore,
        None,
        commit,
        scheme,
        prompt_for_keys=prompt_for_keys,
        push=push,
        update_snapshot_and_timestamp=True,
        reset_updated_targets_on_error=True,
    )


@check_if_clean_and_synced
@log_on_start(DEBUG, "Updating target files", logger=taf_logger)
@log_on_end(DEBUG, "Finished updating target files", logger=taf_logger)
@log_on_error(
    ERROR,
    "An error occurred while updating target files: {e}",
    logger=taf_logger,
    on_exceptions=TAFError,
    reraise=True,
)
def update_and_sign_targets(
    path: str,
    pin_manager: PinManager,
    library_dir: Optional[str],
    target_types: list,
    keystore: str,
    roles_key_infos: str,
    scheme: str,
    commit: Optional[bool] = True,
    prompt_for_keys: Optional[bool] = False,
    push: Optional[bool] = True,
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
    repo_path = Path(path).resolve()
    auth_repo = AuthenticationRepository(path=repo_path, pin_manager=pin_manager)
    keys_name_mappings = read_keys_name_mapping(roles_key_infos)
    auth_repo.add_key_names(keys_name_mappings)

    if library_dir is None:
        library_dir = str(repo_path.parent.parent)  # Ensure this uses the Path object
    repositoriesdb.load_repositories(auth_repo)
    nonexistent_target_types = []
    target_names = []
    for target_type in target_types:
        try:
            targets = repositoriesdb.get_repositories_paths_by_custom_data(
                auth_repo, type=target_type
            )
            if targets is not None:
                target_names.append(targets[0])
            else:
                nonexistent_target_types.append(target_type)
        except Exception:
            nonexistent_target_types.append(target_type)
            continue
    if len(nonexistent_target_types):
        taf_logger.error(
            f"Target types {'.'.join(nonexistent_target_types)} not in repositories.json. Targets not updated"
        )
        return

    # only update target files if all specified types are valid
    for target_name in target_names:
        _save_top_commit_of_repo_to_target(
            Path(library_dir), target_name, repo_path, True
        )
        taf_logger.log("NOTICE", f"Updated {target_name} target file")

    register_target_files(
        repo_path,
        pin_manager,
        keystore,
        roles_key_infos,
        commit,
        push,
        scheme,
        prompt_for_keys=prompt_for_keys,
        reset_updated_targets_on_error=True,
        update_snapshot_and_timestamp=True,
    )


def _update_target_repos(
    repo_path: Path,
    targets_dir: Path,
    target_repo_path: Path,
    add_branch: Optional[bool] = True,
) -> None:
    """Updates target repo's commit sha and branch"""
    if not target_repo_path.is_dir() or target_repo_path == repo_path:
        return
    target_repo = GitRepository(path=target_repo_path)
    if target_repo.is_git_repository:
        head_commit_sha = target_repo.head_commit()
        if head_commit_sha is None:
            taf_logger.warning(
                f"Repository {repo_path} does not have the HEAD reference"
            )
            return
        data = {"commit": head_commit_sha.value}
        if add_branch:
            data["branch"] = target_repo.get_current_branch()
        target_repo_name = target_repo_path.name
        path = targets_dir / target_repo_name
        path.write_text(json.dumps(data, indent=4))
        taf_logger.log("NOTICE", f"Updated {path}")
