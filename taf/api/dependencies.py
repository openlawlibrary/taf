import json
from logging import DEBUG, ERROR
from typing import Dict, Optional
import click
import taf.repositoriesdb as repositoriesdb
from logdecorator import log_on_end, log_on_error, log_on_start
from taf.api.utils._metadata import (
    update_snapshot_and_timestamp,
    update_target_metadata,
)
from taf.api.utils._git import check_if_clean
from taf.messages import git_commit_message
from pathlib import Path

from taf.auth_repo import AuthenticationRepository
from taf.constants import DEFAULT_RSA_SIGNATURE_SCHEME
from taf.exceptions import TAFError
from taf.git import GitRepository
from taf.log import taf_logger
from taf.updater.updater import OperationType, clone_repository
import taf.updater.updater as updater


@log_on_start(
    DEBUG, "Adding or updating dependency {dependency_name:s}", logger=taf_logger
)
@log_on_end(DEBUG, "Finished adding or updating dependency", logger=taf_logger)
@log_on_error(
    ERROR,
    "An error occurred while adding a new dependency: {e}",
    logger=taf_logger,
    on_exceptions=TAFError,
    reraise=True,
)
@check_if_clean
def add_dependency(
    path: str,
    dependency_name: str,
    branch_name: str,
    out_of_band_commit: str,
    keystore: str,
    dependency_path: Optional[str] = None,
    dependency_url: Optional[str] = None,
    library_dir: Optional[str] = None,
    scheme: Optional[str] = DEFAULT_RSA_SIGNATURE_SCHEME,
    custom: Optional[Dict] = None,
    prompt_for_keys: Optional[bool] = False,
    commit: Optional[bool] = True,
    push: Optional[bool] = True,
    no_prompt: Optional[bool] = False,
) -> None:
    """
    Add a dependency (an authentication repository) to dependencies.json or update it if it was already added to this file.
    Information that is added to dependencies.json includes out-of-band authentication commit name of the branch which contains
    that commit. It is possible for multiple branches to contain the same commit, so it's important to list branch name as well.
    If repository exists on disk, this function also validates that out_of_brand_commit and branch_name exist and that the
    commit belongs to the specified branch.

    Arguments:
        path: Path to the authentication repository.
        dependency_name: Name of the dependency.
        branch_name: Name of the branch which contains the out-of-band authentication commit.
        out_of_band_commit: SHA of out-of-band authentication commit.
        keystore: Location of the keystore files.
        dependency_path (optional): Path to the dependency repository which is to be added. Can be omitted if dependency_name
        library_dir (optional): Path to the library's root directory. Determined based on the authentication repository's path if not provided.
        scheme (optional): Signing scheme. Set to rsa-pkcs1v15-sha256 by default.
        custom (optional): Additional data that will be added to dependencies.json if specified.
        prompt_for_keys (optional): Whether to ask the user to enter their key if it is not located inside the keystore directory.
        commit (optional): Indicates if the changes should be committed and pushed automatically.
        push (optional): Flag specifying whether to push to remote.
        no_prompt (optional): Flag specifying whether to ask the user to confirm branch and commit values is they are not specified.
    Side Effects:
        Updates dependencies.json, targets, snapshot and timestamp metadata, writes changes to disk
        and commits them.

    Raises:
        TAFError if dependency exists on disk, but does not contain specified commit and/or branch

    Returns:
        None
    """
    if path is None:
        raise TAFError("Authentication repository's path not provided")

    auth_repo = AuthenticationRepository(path=path)
    if not auth_repo.is_git_repository_root:
        taf_logger.error(f"{path} is not a git repository!")
        return

    dependencies_json = repositoriesdb.load_dependencies_json(auth_repo)
    if dependencies_json is not None and dependency_name in dependencies_json:
        taf_logger.log("NOTICE", f"{dependency_name} already added")
        return
    if library_dir is None:
        library_dir = str(auth_repo.path.parent.parent)

    if dependency_path is not None:
        dependency = GitRepository(path=dependency_path)
    else:
        dependency = GitRepository(library_dir, dependency_name)

    if not dependency.is_git_repository and dependency_url is not None:
        taf_logger.log(
            "NOTICE", f"{dependency.path} does not exist. Cloning from {dependency_url}"
        )
        config = updater.UpdateConfig(
            operation=OperationType.CLONE,
            url=dependency_url,
            path=Path(library_dir, dependency_name),
            library_dir=library_dir,
            strict=False,
            bare=False,
            no_deps=False,
        )  # type: ignore
        try:
            clone_repository(config)
            dependency.default_branch = dependency._determine_default_branch()
        except Exception as e:
            taf_logger.error(f"Dependency clone failed due to error {e}.")
            return

    if dependency.is_git_repository:
        branch_name, out_of_band_commit = _determine_out_of_band_data(
            dependency, branch_name, out_of_band_commit, no_prompt
        )
    else:
        if branch_name is None or out_of_band_commit is None:
            raise TAFError(
                "Branch name and out-of-band commit must be specified if repository does not exist on disk"
            )
        if not no_prompt and not click.confirm(
            "Dependency not on disk. Proceed without validating branch and commit?"
        ):
            return

    # add to dependencies.json or update the entry
    dependencies_json = repositoriesdb.load_dependencies_json(auth_repo)

    # if dependencies.json does not exist, initialize it
    if not dependencies_json:
        dependencies_json = {"dependencies": {}}

    dependencies = dependencies_json["dependencies"]
    if dependency_name in dependencies:
        print(f"{dependency_name} already added to dependencies.json. Overwriting")
    dependencies[dependency_name] = {
        "out-of-band-authentication": out_of_band_commit,
        "branch": branch_name,
    }
    if custom:
        dependencies[dependency_name]["custom"] = custom

    # update content of repositories.json before updating targets metadata
    dependencies_path = Path(auth_repo.path, repositoriesdb.DEPENDENCIES_JSON_PATH)
    dependencies_path.parent.mkdir(exist_ok=True)
    Path(dependencies_path).write_text(json.dumps(dependencies_json, indent=4))

    removed_targets_data: Dict = {}
    added_targets_data: Dict = {repositoriesdb.DEPENDENCIES_JSON_NAME: {}}
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
        commit_msg = git_commit_message(
            "add-dependency", dependency_name=dependency_name
        )
        auth_repo.commit_and_push(commit_msg=commit_msg, push=push)
    else:
        print("\nPlease commit manually.\n")


@log_on_start(DEBUG, "Remove dependency {dependency_name:s}", logger=taf_logger)
@log_on_end(DEBUG, "Finished removing dependency", logger=taf_logger)
@log_on_error(
    ERROR,
    "An error occurred while removing a dependency: {e}",
    logger=taf_logger,
    on_exceptions=TAFError,
    reraise=True,
)
@check_if_clean
def remove_dependency(
    path: str,
    dependency_name: str,
    keystore: str,
    scheme: Optional[str] = DEFAULT_RSA_SIGNATURE_SCHEME,
    prompt_for_keys: Optional[bool] = False,
    commit: Optional[bool] = True,
    push: Optional[bool] = True,
) -> None:
    """
    Remove a dependency (an authentication repository) from dependencies.json

    Arguments:
        path: Path to the authentication repository.
        dependency_name: Name of the dependency which should be removed.
        keystore: Location of the keystore files.
        scheme (optional): Signing scheme. Set to rsa-pkcs1v15-sha256 by default.
        prompt_for_keys (optional): Whether to ask the user to enter their key if it is not located inside the keystore directory.
        commit (optional): Indicates if the changes should be committed and pushed automatically.
        push (optional): Flag specifying whether to push to remote
    Side Effects:
        Updates dependencies.json, targets, snapshot and timestamp metadata, writes changes to disk
        and commits them.

    Returns:
        None
    """
    if path is None:
        raise TAFError("Authentication repository's path not provided")

    auth_repo = AuthenticationRepository(path=path)
    if not auth_repo.is_git_repository_root:
        print(f"{path} is not a git repository!")
        return

    # add to dependencies.json or update the entry
    dependencies_json = repositoriesdb.load_dependencies_json(auth_repo)

    if not dependencies_json:
        print("dependencies.json does not exist")
        return

    dependencies = dependencies_json["dependencies"]

    if dependency_name not in dependencies:
        print("Dependency not in dependencies.json")
        return

    dependencies.pop(dependency_name)

    # update content of repositories.json before updating targets metadata
    Path(auth_repo.path, repositoriesdb.DEPENDENCIES_JSON_PATH).write_text(
        json.dumps(dependencies_json, indent=4)
    )

    removed_targets_data: Dict = {}
    added_targets_data: Dict = {repositoriesdb.DEPENDENCIES_JSON_NAME: {}}
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
        commit_msg = git_commit_message(
            "remove-dependency", dependency_name=dependency_name
        )
        auth_repo.commit_and_push(commit_msg=commit_msg, push=push)
    else:
        print("\nPlease commit manually.\n")


def _determine_out_of_band_data(
    dependency: GitRepository,
    branch_name: str,
    out_of_band_commit: str,
    no_prompt: Optional[bool] = False,
):
    """
    Determines values of out-of-band branch and commit as a part of adding a new
    dependency to dependencies.json. If not defined, branch is set to the default branch
    of the repository and commit to the first commit of that branch.
    """
    is_branch_specified = branch_name is not None
    is_commit_specified = out_of_band_commit is not None

    if branch_name is None:
        branch_name = dependency.default_branch
    else:
        if not dependency.branch_exists(branch_name):
            raise TAFError(f"Branch {branch_name} does not exists in {dependency.name}")

    if out_of_band_commit is None:
        out_of_band_commit = dependency.get_first_commit_on_branch(branch_name)
    else:
        try:
            branches = dependency.branches_containing_commit(
                out_of_band_commit, strip_remote=True
            )
        except TAFError:
            raise TAFError("Specified out-of-band authentication commit does not exist")
        if branch_name not in branches:
            raise TAFError(f"Commit {out_of_band_commit} not on branch {branch_name}")

    if not no_prompt and (not is_branch_specified or not is_commit_specified):
        if not click.confirm(
            f"Branch and out-of-band authentication commit will be set to {branch_name} and {out_of_band_commit}. Proceed?"
        ):
            return

    return branch_name, out_of_band_commit
