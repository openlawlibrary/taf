"""
The general idea of the updater is the following:
- We have a git repository which contains the metadata files. These metadata files
are in the 'metadata' directory
- Clients have a clone of that repository on their local machine and want to update it
- We don't want to simply pull the updates. We want to verify that the new commits
(committed after the most recent one in the client's local repository)
- For each of the new commits, we want to check if all metadata is valid. The set of
metadata should be valid as a whole at that revision. Not only do we want to make sure
that a metadata which is supposed to be changed was indeed updated and is valid, but
also to make sure that if a metadata file should not be updated, it remained the same.
- We also want to make sure that all targets metadata is valid (including the delegated roles)
- We do not want to simply update the metadata to the latest version, without skipping
these checks. We want to check each commit, not just the last one.
- If we are checking a commit which is not the latest one, we do not want to report an error
if the metadata expired. We want to make sure that that was valid at the time when the
metadata was committed.
- We can rely on the TUF's way of handling metadata, by using the current and previous
directories. We just want to automatically create and update them. They should not
remain on the client's machine.
- We do not want to modify TUF's updater to much, but still need to get around the fact
that TUF skips mirrors which do not have valid and/or current metadata files. Also, we
do not simply want to find the latest metadata, we want to validate everything in-between.
That is why the idea is to call refresh multiple times, until the last commit is reached.
The 'GitUpdater' updater is designed in such a way that for each new call it
loads data from a most recent commit.
"""
import copy
from logging import ERROR

from typing import Dict, Tuple, Any
from attr import define, field
from logdecorator import log_on_error
from taf.auth_repo import AuthenticationRepository
from taf.git import GitRepository
from taf.updater.types.update import OperationType, UpdateType
from taf.updater.updater_pipeline import (
    AuthenticationRepositoryUpdatePipeline,
)

from pathlib import Path
from taf.log import taf_logger
import taf.repositoriesdb as repositoriesdb
from taf.utils import is_non_empty_directory, timed_run
import taf.settings as settings
from taf.exceptions import (
    ScriptExecutionError,
    UpdateFailedError,
    ValidationFailedError,
)

from taf.updater.lifecycle_handlers import (
    handle_repo_event,
    handle_update_event,
    Event,
)
from cattr import unstructure
import concurrent.futures
from concurrent.futures import ThreadPoolExecutor
from taf.updater.types.update import Update


def _check_update_status(repos_update_data: Dict[str, Any]) -> Tuple[Event, str]:
    # helper function to set update status of update handler based on repo status.
    # if repo handlers event status changed,
    # change the update handler status
    update_status = Event.UNCHANGED
    errors = ""

    for auth_repo_name in repos_update_data:
        repo_update_data = repos_update_data[auth_repo_name]
        repo_update_status = repo_update_data["update_status"]
        if update_status != repo_update_status and update_status != Event.FAILED:
            # if one failed, then failed
            # else if one changed, then changed
            # else unchanged
            update_status = repo_update_status
        repo_error = repo_update_data["error"]
        if repo_error is not None:
            errors += str(repo_error)

    return update_status, errors


def _execute_repo_handlers(
    update_status,
    auth_repo,
    scripts_root_dir,
    commits_data,
    error,
    warnings,
    targets_data,
    transient_data,
):
    try:
        transient = handle_repo_event(
            update_status,
            None,
            auth_repo.library_dir,
            scripts_root_dir,
            auth_repo,
            commits_data,
            error,
            warnings,
            targets_data,
        )
        if transient_data is not None:
            transient_data.update(transient)
    except ScriptExecutionError as e:
        if settings.development_mode:
            _reset_to_commits_before_pull(auth_repo, commits_data, targets_data)
            error = e


def _reset_to_commits_before_pull(auth_repo, commits_data, targets_data):
    taf_logger.info(
        "In development mode. Resetting repositories to commits before pull after handler failure"
    )

    def _reset_repository(repo, commits_data):
        before_pull = commits_data.before_pull
        after_pull = commits_data.after_pull
        if before_pull == after_pull:
            return
        repo.reset_to_commit(before_pull, hard=True)

    auth_repo.checkout_branch(auth_repo.default_branch)
    _reset_repository(auth_repo, commits_data)
    auth_repo.set_last_validated_commit(commits_data.before_pull)

    for repo_name, repo_data in targets_data.items():
        repo = repositoriesdb.get_repository(auth_repo, repo_name)
        for branch, branch_data in repo_data["commits"].items():
            repo.checkout_branch(branch)
            _reset_repository(repo, branch_data)


@define
class UpdateConfig:
    operation: OperationType = field(converter=OperationType)
    remote_url: str = field(
        metadata={"docs": "Remote URL of the remote authentication repository"},
        default=None,
    )
    path: Path = field(
        default=None,
        converter=lambda p: Path(p).resolve() if p else None,
        metadata={"docs": "Client's authentication repository's full path"},
    )
    library_dir: Path = field(
        default=None,
        metadata={
            "docs": "Directory where client's target repositories are located. Optional."
        },
    )
    update_from_filesystem: bool = field(
        default=False,
        metadata={
            "docs": "A flag indicating if the URL is actually a file system path. Optional."
        },
    )
    expected_repo_type: UpdateType = field(
        default=UpdateType.EITHER,
        metadata={
            "docs": "Indicates if the repository is a test, official, or any type. Optional."
        },
    )
    target_repo_classes: object = field(
        default=None,
        metadata={
            "docs": "A class or dictionary used for instantiating target repositories. Optional."
        },
    )
    target_factory: object = field(
        default=None,
        metadata={
            "docs": "A git repositories factory used for instantiating target repositories. Optional."
        },
    )
    only_validate: bool = field(
        default=False,
        metadata={
            "docs": "Specifies if repositories should only be validated without being updated. Optional."
        },
    )
    validate_from_commit: str = field(
        default=None,
        metadata={"docs": "Commit from which validation should start. Optional."},
    )
    out_of_band_authentication: str = field(
        default=None,
        metadata={"docs": "Out-of-band authentication commit's SHA. Optional."},
    )
    scripts_root_dir: Path = field(
        default=None,
        metadata={
            "docs": "Local directory for script testing, not in the authentication repository. Optional."
        },
    )
    checkout: bool = field(
        default=True,
        metadata={
            "docs": "Whether to checkout last validated commits after update. Optional."
        },
    )
    clone_urls: list = field(
        default=None,
        metadata={"docs": "List of URLs to clone repositories from. Optional."},
    )
    excluded_target_globs: list = field(
        default=None,
        metadata={
            "docs": "Globs specifying target repositories to exclude from validation and update. Optional."
        },
    )
    strict: bool = field(
        default=False,
        metadata={"docs": "Whether update fails if a warning is raised. Optional."},
    )
    bare: bool = field(
        default=False,
        metadata={
            "docs": "Whether to clone repositories as bare repositories. If set to true, all repositories will be cloned as bare repositories. Optional."
        },
    )
    force: bool = field(
        default=False,
        metadata={
            "docs": "Whether to force update repositories. If set to true, all repositories will be forcefully updated."
        },
    )
    no_deps: bool = field(
        default=False,
        metadata={"docs": "Specifies whether or not to update dependencies. Optional."},
    )
    no_targets: bool = field(
        default=False,
        metadata={
            "docs": "Flag to skip target repositiory validation and validate only authentication repos. Optional."
        },
    )
    no_upstream: bool = field(
        default=True,
        metadata={
            "docs": "Flag to skip comparison with remote repositories upstream. Optional."
        },
    )
    run_scripts: bool = field(
        default=False,
        metadata={"docs": "Run the auxiliary lifecycle handler scripts. Optional."},
    )

    def __attrs_post_init__(self):
        if self.operation == OperationType.CLONE:
            if self.library_dir is None:
                if self.path:
                    self.library_dir = self.path.parent.parent
                else:
                    self.library_dir = Path(".").resolve()

        if self.operation == OperationType.UPDATE:
            if self.path is None:
                self.path = Path(".").resolve()
            if self.library_dir is None:
                self.library_dir = self.path.parent.parent


@log_on_error(
    ERROR,
    "{e}",
    logger=taf_logger,
    on_exceptions=UpdateFailedError,
    reraise=True,
)
@timed_run("Cloning repositories")
def clone_repository(config: UpdateConfig):
    """
    Validate and clone an authentication repository and its target repositories, as well
    as its dependencies (linked authentication repositories and their targets) recursively.
    Arguments:
        config: UpdateConfig instance containing all configurations.

    Side Effects:
        If only_validate is not set to True, updates authentication repository (pulls new changes) and its target
        repositories and dependencies

    Returns:
        None
    """
    settings.strict = config.strict
    settings.run_scripts = config.run_scripts

    if config.remote_url is None:
        raise UpdateFailedError(
            "Remote URL has to be specified when cloning repositories"
        )

    if config.path and is_non_empty_directory(config.path):
        raise UpdateFailedError(
            f"Destination path {config.path} already exists and is not an empty directory. Run 'taf repo update' to update it."
        )

    config.operation = OperationType.CLONE
    return _update_or_clone_repository(config)


@log_on_error(
    ERROR,
    "{e}",
    logger=taf_logger,
    on_exceptions=UpdateFailedError,
    reraise=True,
)
@timed_run("Updating repository")
def update_repository(config: UpdateConfig):
    """
    Validate and update an authentication repository and its target repositories, as well
    as its dependencies (linked authentication repositories and their targets) recursively.

    Arguments:
        config: UpdateConfig instance containing all configurations.

    Side Effects:
        If only_validate is not set to True, updates authentication repository (pulls new changes) and its target
        repositories and dependencies

    Returns:
        None
    """
    settings.strict = config.strict
    settings.run_scripts = config.run_scripts

    # if path is not specified, name should be read from info.json
    # which is available after the remote repository is cloned and validated

    auth_repo = GitRepository(path=config.path)
    if not config.path.is_dir() or not auth_repo.is_git_repository:
        raise UpdateFailedError(
            f"{config.path} is not a Git repository. Run 'taf repo clone' instead"
        )

    taf_logger.info(f"Updating repository {auth_repo.name}")

    if config.remote_url is None:
        config.remote_url = auth_repo.get_remote_url()
        if config.remote_url is None:
            raise UpdateFailedError("URL cannot be determined. Please specify it")

    if auth_repo.is_bare_repository:
        # Handle updates for bare repositories
        config.bare = True
    return _update_or_clone_repository(config)


def _update_or_clone_repository(config: UpdateConfig):
    repos_update_data: Dict = {}
    transient_data: Dict = {}
    root_error = None
    auth_repo_name = None
    try:
        updater_pipeline = AuthenticationRepositoryUpdatePipeline(config)
        updater_pipeline.run()
        update_output = updater_pipeline.output
        auth_repo_name = update_output.auth_repo_name
        _process_repo_update(
            update_config=config,
            update_output=update_output,
            repos_update_data=repos_update_data,
            transient_data=transient_data,
        )
        if repos_update_data[auth_repo_name].get("error"):
            raise repos_update_data[auth_repo_name]["error"]

    except Exception as e:
        root_error = UpdateFailedError(
            f"Update of {auth_repo_name or 'repository'} failed due to error: {e}"
        )

    update_data = Update()

    if auth_repo_name is None or auth_repo_name not in repos_update_data:
        # this must mean that an error occurred
        if root_error is not None:
            raise root_error
        else:
            raise UpdateFailedError(f"Update of {auth_repo_name} failed")

    # after all repositories have been updated
    # update information is in repos_update_data
    root_auth_repo = repos_update_data[auth_repo_name]["auth_repo"]

    update_status, errors = _check_update_status(repos_update_data)
    update_transient_data = _update_transient_data(transient_data, repos_update_data)

    update_data = handle_update_event(
        update_status,
        update_transient_data,
        root_auth_repo.library_dir,
        config.scripts_root_dir,
        repos_update_data,
        errors,
        root_auth_repo,
    )
    if repos_update_data[auth_repo_name].get("warnings"):
        taf_logger.warning(repos_update_data[auth_repo_name].get("warnings"))

    log_repo_updates(update_data)

    if root_error:
        raise root_error
    return unstructure(update_data)


def _process_repo_update(
    update_config,
    update_output,
    visited=None,
    repos_update_data=None,
    transient_data=None,
):
    """
    Arguments:
        update_config: update configuration object containing all relevant information, like remote url, operation type, local paths
        visited (optional): Authentication repositories which were already processed
        repos_update_data (optional): update status, commits data, targets data of the repository which was updated
        transient_data (optinal): data passed from one lifecycle handler to the next one

    """

    if visited is None:
        visited = []
    # if there is a recursive dependency
    if update_config.remote_url in visited:
        return
    visited.append(update_config.remote_url)
    # at the moment, we assume that the initial commit is valid and that it contains at least root.json
    update_status = update_output.event
    auth_repo = update_output.users_auth_repo
    commits_data = update_output.commits_data
    error = update_output.error
    warnings = update_output.warnings
    targets_data = (update_output.targets_data,)

    # if auth_repo doesn't exist, means that either clients-auth-path isn't provided,
    # or info.json is missing from protected
    if auth_repo is None:
        raise error

    # if commits_data is empty, do not attempt to load the dependencies
    # that can happen in the repository didn't exists, but could not be validated
    # and was therefore deleted
    # or if the last validated commit is not equal to the top commit, meaning that
    # the repository was updated without using the updater
    # this second case could be reworked to return the state as of the last validated commit
    # but treat the repository as invalid for now
    commits = []

    if commits_data.after_pull is not None:
        if commits_data.before_pull is not None:
            commits = [commits_data.before_pull]
        commits.extend(commits_data.new)

    if commits_data.after_pull is not None and not update_config.no_deps:

        if update_status != Event.FAILED:
            # for now, just take the newest commit and do not worry about updated definitions
            # latest_commit = commits[-1::]
            repositoriesdb.load_dependencies(
                auth_repo,
                library_dir=update_config.library_dir,
                commits=commits,
            )

            # load the repositories from dependencies.json and update these repositories
            child_auth_repos = repositoriesdb.get_deduplicated_auth_repositories(
                auth_repo, commits
            ).values()
            outputs, errors = _update_dependencies(update_config, child_auth_repos)
            if len(errors):
                errors = "\n".join(errors)
                taf_logger.error(
                    "Update of {} failed. One or more referenced authentication repositories could not be validated:\n {}",
                    auth_repo.name,
                    errors,
                )
                error = UpdateFailedError(
                    f"Update of {auth_repo.name} failed. One or more referenced authentication repositories could not be validated:\n {errors}"
                )
            for output in outputs:
                child_update_status = output.event
                if child_update_status == Event.FAILED:
                    update_status = Event.FAILED
                repo = output.users_auth_repo
                child_config = copy.copy(update_config)
                child_config.remote_url = repo.urls[0]
                child_config.clone_urls = repo.urls
                child_config.out_of_band_authentication = (
                    repo.out_of_band_authentication
                )
                child_config.path = repo.path
                _process_repo_update(
                    child_config, output, visited, repos_update_data, transient_data
                )

        # do not call the handlers if only validating the repositories
        # if a handler fails and we are in the development mode, revert the update
        # so that it's easy to try again after fixing the handler
        if (
            not update_config.only_validate
            and not update_config.excluded_target_globs
            and not update_config.no_targets
        ):
            _execute_repo_handlers(
                update_status,
                auth_repo,
                update_config.scripts_root_dir,
                commits_data,
                error,
                warnings,
                targets_data,
                transient_data,
            )

    if repos_update_data is not None:
        repos_update_data[auth_repo.name] = {
            "auth_repo": auth_repo,
            "update_status": update_status,
            "commits_data": commits_data,
            "error": error,
            "warnings": warnings,
            "targets_data": targets_data,
        }

    repositoriesdb.clear_repositories_db()


def log_repo_updates(update_data: Update):
    """
    Log the status of the repositories after updating them.
    """
    update_output_dict = {
        repo_name: {
            "changed": repo_info["changed"],
            "event": repo_info["event"],
            **({"warning": repo_info["warnings"]} if "warnings" in repo_info else {}),
            **({"error": repo_info["error_msg"]} if repo_info["error_msg"] else {}),
        }
        for repo_name, repo_info in update_data.auth_repos.items()
    }
    changes_or_errors = False

    for repo_name, details in update_output_dict.items():
        changed = details.get("changed", False)
        event_operation = details["event"]
        error_message = details.get("error")

        if changed or error_message:
            changes_or_errors = True
            message = f"Repository: {repo_name}\n"
            message += f"  Change status: {'changed' if changed else 'no changes'}\n"
            message += f"  Event: {event_operation}"

            if error_message:
                message += f"\n  Error: {error_message}\n"

            taf_logger.log("NOTICE", message)

    if not changes_or_errors:
        taf_logger.log(
            "NOTICE", "All repositories are up-to-date with no changes or errors."
        )


def _update_dependencies(update_config, child_auth_repos):

    # for now, just take the newest commit and do not worry about updated definitions
    # latest_commit = commits[-1::]
    outputs = []
    errors = []

    def _update_child_repo(updater_pipeline):
        try:
            updater_pipeline.run()
            output = updater_pipeline.output
            error = output.error
            return output, error
        except Exception as e:
            return None, e

    with ThreadPoolExecutor() as executor:
        futures = {}
        for repo in child_auth_repos:
            child_config = copy.copy(update_config)
            child_config.operation = (
                OperationType.UPDATE if repo.is_git_repository else OperationType.CLONE
            )
            child_config.remote_url = repo.urls[0]
            child_config.clone_urls = repo.urls
            child_config.out_of_band_authentication = repo.out_of_band_authentication
            child_config.path = repo.path
            pipeline = AuthenticationRepositoryUpdatePipeline(child_config)
            future = executor.submit(_update_child_repo, pipeline)
            futures[future] = repo

        for future in concurrent.futures.as_completed(futures):
            output, error = future.result()
            if error:
                errors.append(str(error))
            if output:
                outputs.append(output)
    return outputs, errors


def _update_transient_data(
    transient_data, repos_update_data: Dict[str, str]
) -> Dict[str, Any]:
    update_transient_data = {}
    for auth_repo_name in repos_update_data:
        if auth_repo_name in transient_data:
            update_transient_data[auth_repo_name] = transient_data[auth_repo_name]
    return update_transient_data


@timed_run("Validating repository")
def validate_repository(
    auth_path,
    library_dir=None,
    validate_from_commit=None,
    excluded_target_globs=None,
    strict=False,
    bare=False,
    no_targets=False,
    no_deps=False,
):
    settings.strict = strict

    auth_path = Path(auth_path).resolve()

    if library_dir is None:
        library_dir = auth_path.parent.parent
    else:
        library_dir = Path(library_dir).resolve()

    auth_repo = AuthenticationRepository(path=auth_path)
    expected_repo_type = (
        UpdateType.TEST if auth_repo.is_test_repo else UpdateType.OFFICIAL
    )

    auth_repo_name = None

    try:
        config = UpdateConfig(
            operation=OperationType.UPDATE,
            remote_url=str(auth_path),
            path=auth_path,
            library_dir=library_dir,
            validate_from_commit=validate_from_commit,
            excluded_target_globs=excluded_target_globs,
            strict=strict,
            bare=bare,
            no_targets=no_targets,
            no_deps=no_deps,
            expected_repo_type=expected_repo_type,
            update_from_filesystem=True,
            only_validate=True,
        )
        updater_pipeline = AuthenticationRepositoryUpdatePipeline(config)
        updater_pipeline.run()
        update_output = updater_pipeline.output
        auth_repo_name = update_output.auth_repo_name
        if update_output.error:
            raise update_output.error

        _process_repo_update(
            config,
            update_output,
        )
    except Exception as e:
        raise ValidationFailedError(
            f"Validation of repository {auth_repo_name or ''} failed due to error: {e}"
        )
    settings.last_validated_commit = {}
