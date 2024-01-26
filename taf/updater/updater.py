from logging import ERROR

from typing import Dict, Tuple, Any
from attr import define, field
from logdecorator import log_on_error
from taf.git import GitRepository
from taf.updater.types.update import OperationType, UpdateType
from taf.updater.updater_pipeline import (
    AuthenticationRepositoryUpdatePipeline,
    _merge_commit,
)

from pathlib import Path
from taf.log import taf_logger, disable_tuf_console_logging
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


disable_tuf_console_logging()


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
        before_pull = commits_data["before_pull"]
        if isinstance(before_pull, dict):
            before_pull = before_pull["commit"]
        after_pull = commits_data["after_pull"]
        if isinstance(after_pull, dict):
            after_pull = after_pull["commit"]
        if before_pull == after_pull:
            return
        repo.reset_to_commit(before_pull, hard=True)

    auth_repo.checkout_branch(auth_repo.default_branch)
    _reset_repository(auth_repo, commits_data)
    auth_repo.set_last_validated_commit(commits_data["before_pull"])

    for repo_name, repo_data in targets_data.items():
        repo = repositoriesdb.get_repository(auth_repo, repo_name)
        for branch, branch_data in repo_data["commits"].items():
            repo.checkout_branch(branch)
            _reset_repository(repo, branch_data)


@define
class RepositoryConfig:
    operation: OperationType = field(converter=OperationType)
    url: str = field(
        metadata={"docs": "URL of the remote authentication repository"}, default=None
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
def clone_repository(config: RepositoryConfig):
    """
    Validate and clone an authentication repository and its target repositories, as well
    as its dependencies (linked authentication repositories and their targets) recursively.
    Arguments:
        config: RepositoryConfig instance containing all configurations.

    Side Effects:
        If only_validate is not set to True, updates authentication repository (pulls new changes) and its target
        repositories and dependencies

    Returns:
        None
    """
    settings.strict = config.strict

    if config.url is None:
        raise UpdateFailedError("URL has to be specified when cloning repositories")

    if config.path and is_non_empty_directory(config.path):
        raise UpdateFailedError(
            f"Destination path {config.path} already exists and is not an empty directory. Run `taf repo update` to update it."
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
def update_repository(config: RepositoryConfig):
    """
    Validate and update an authentication repository and its target repositories, as well
    as its dependencies (linked authentication repositories and their targets) recursively.

    Arguments:
        config: RepositoryConfig instance containing all configurations.

    Side Effects:
        If only_validate is not set to True, updates authentication repository (pulls new changes) and its target
        repositories and dependencies

    Returns:
        None
    """
    settings.strict = config.strict

    # if path is not specified, name should be read from info.json
    # which is available after the remote repository is cloned and validated

    auth_repo = GitRepository(path=config.path)
    if not config.path.is_dir() or not auth_repo.is_git_repository:
        raise UpdateFailedError(
            f"{config.path} is not a Git repository. Run `taf repo clone` instead"
        )

    taf_logger.info(f"Updating repository {auth_repo.name}")

    if config.url is None:
        config.url = auth_repo.get_remote_url()
        if config.url is None:
            raise UpdateFailedError("URL cannot be determined. Please specify it")

    return _update_or_clone_repository(config)


def _update_or_clone_repository(config: RepositoryConfig):
    repos_update_data: Dict = {}
    transient_data: Dict = {}
    root_error = None
    auth_repo_name = None
    try:

        auth_repo_name, error = _update_named_repository(
            config.operation,
            config.url,
            config.path,
            config.library_dir,
            config.update_from_filesystem,
            config.expected_repo_type,
            config.target_repo_classes,
            config.target_factory,
            config.only_validate,
            config.validate_from_commit,
            None,
            repos_update_data=repos_update_data,
            transient_data=transient_data,
            out_of_band_authentication=config.out_of_band_authentication,
            scripts_root_dir=config.scripts_root_dir,
            checkout=config.checkout,
            excluded_target_globs=config.excluded_target_globs,
        )
        if error:
            raise error
    except Exception as e:
        root_error = UpdateFailedError(
            f"Update of {auth_repo_name or 'repository'} failed due to error: {e}"
        )

    update_data = {}
    if not config.excluded_target_globs:
        # after all repositories have been updated
        # update information is in repos_update_data
        if auth_repo_name is None or auth_repo_name not in repos_update_data:
            # this must mean that an error occurred
            if root_error is not None:
                raise root_error
            else:
                raise UpdateFailedError(f"Update of {auth_repo_name} failed")
        root_auth_repo = repos_update_data[auth_repo_name]["auth_repo"]

        update_status, errors = _check_update_status(repos_update_data)
        update_transient_data = _update_transient_data(
            transient_data, repos_update_data
        )

        update_data = handle_update_event(
            update_status,
            update_transient_data,
            root_auth_repo.library_dir,
            config.scripts_root_dir,
            repos_update_data,
            errors,
            root_auth_repo,
        )

    if root_error:
        raise root_error
    return unstructure(update_data)


def _update_named_repository(
    operation,
    url,
    auth_path,
    library_dir,
    update_from_filesystem,
    expected_repo_type,
    target_repo_classes=None,
    target_factory=None,
    only_validate=False,
    validate_from_commit=None,
    conf_directory_root=None,
    visited=None,
    repos_update_data=None,
    transient_data=None,
    out_of_band_authentication=None,
    scripts_root_dir=None,
    checkout=True,
    excluded_target_globs=None,
):
    """
    Arguments:
        url: URL of the remote authentication repository
        clients_library_dir: Directory where client's target repositories are located.
        auth_repo_name: Authentication repository's name
        update_from_filesystem (optional): A flag which indicates if the URL is actually a file system path
        expected_repo_type (optional): Indicates if the authentication repository which needs to be updated is
            a test repository, official repository, or if the type is not important
            and should not be validated
        target_repo_classes (optional): A class or a dictionary used when instantiating target repositories.
            See repositoriesdb load_repositories for more details
        target_factory: A git repositories factory used when instantiating target repositories.
            See repositoriesdb load_repositories for more details
        only_validate (optional): a flag that specifies if the repositories should only be validated without
            being updated
        validate_from_commit (optional): commit from which the validation should start, allowing shorter
            execution time
        visited (optional): Authentication repositories which were already processed
        repos_update_data (optional): update status, commits data, targets data of the repository which was updated
        out_of_band_authentication (optional): out-of-band authentication commit's sha
        scripts_root_dir (optional): local directory which does not have to be contained by the authentication
            repository. Used for testing purposes while developing the scripts
        checkout (optional): Whether to checkout last validated commits after update is done
        excluded_target_globs (options): globs specifying target repositories which should not get validated and updated.
        strict (optional): Whether or not update fails if a warning is raised

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
    if visited is None:
        visited = []
    # if there is a recursive dependency
    if url in visited:
        return
    visited.append(url)
    # at the moment, we assume that the initial commit is valid and that it contains at least root.json
    (
        update_status,
        auth_repo,
        auth_repo_name,
        commits_data,
        error,
        targets_data,
    ) = _update_current_repository(
        operation,
        url,
        auth_path,
        library_dir,
        update_from_filesystem,
        expected_repo_type,
        target_repo_classes,
        target_factory,
        only_validate,
        validate_from_commit,
        conf_directory_root,
        out_of_band_authentication,
        checkout,
        excluded_target_globs,
    )

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
    if commits_data["after_pull"] is not None:
        if commits_data["before_pull"] is not None:
            commits = [commits_data["before_pull"]]
        commits.extend(commits_data["new"])
        # TODO
        # need to handle wrong definitions and make sure that the update doesn't fail
        # for now, just take the newest commit and do not worry about updated definitions
        # latest_commit = commits[-1::]
        repositoriesdb.load_dependencies(
            auth_repo,
            library_dir=library_dir,
            commits=commits,
        )

        if update_status != Event.FAILED:
            errors = []
            # load the repositories from dependencies.json and update these repositories
            child_auth_repos = repositoriesdb.get_deduplicated_auth_repositories(
                auth_repo, commits
            ).values()

            for child_auth_repo in child_auth_repos:
                try:
                    _, error = _update_named_repository(
                        operation=OperationType.CLONE_OR_UPDATE,
                        url=child_auth_repo.urls[0],
                        auth_path=child_auth_repo.path,
                        library_dir=library_dir,
                        update_from_filesystem=update_from_filesystem,
                        expected_repo_type=expected_repo_type,
                        target_repo_classes=target_repo_classes,
                        target_factory=target_factory,
                        only_validate=only_validate,
                        validate_from_commit=validate_from_commit,
                        conf_directory_root=conf_directory_root,
                        visited=visited,
                        repos_update_data=repos_update_data,
                        transient_data=transient_data,
                        out_of_band_authentication=child_auth_repo.out_of_band_authentication,
                        scripts_root_dir=scripts_root_dir,
                        checkout=checkout,
                    )
                    if error:
                        raise error
                except Exception as e:
                    errors.append(str(e))

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
                update_status = Event.FAILED

        if (
            not only_validate
            and len(commits)
            and (update_status == Event.CHANGED or update_status == Event.PARTIAL)
        ):
            # when performing breadth-first update, validation might fail at some point
            # but we want to update all repository up to it
            # so set last validated commit to this last valid commit
            last_commit = commits[-1]
            # if there were no errors, merge the last validated authentication repository commit
            _merge_commit(
                auth_repo, auth_repo.default_branch, last_commit, checkout, True
            )
            # update the last validated commit
            if not excluded_target_globs:
                auth_repo.set_last_validated_commit(last_commit)

        # do not call the handlers if only validating the repositories
        # if a handler fails and we are in the development mode, revert the update
        # so that it's easy to try again after fixing the handler
        if not only_validate and not excluded_target_globs:
            _execute_repo_handlers(
                update_status,
                auth_repo,
                scripts_root_dir,
                commits_data,
                error,
                targets_data,
                transient_data,
            )
    if repos_update_data is not None:
        repos_update_data[auth_repo.name] = {
            "auth_repo": auth_repo,
            "update_status": update_status,
            "commits_data": commits_data,
            "error": error,
            "targets_data": targets_data,
        }

    repositoriesdb.clear_repositories_db()

    return auth_repo_name, error


def _update_current_repository(
    operation,
    url,
    auth_path,
    library_dir,
    update_from_filesystem,
    expected_repo_type,
    target_repo_classes,
    target_factory,
    only_validate,
    validate_from_commit,
    conf_directory_root,
    out_of_band_authentication,
    checkout,
    excluded_target_globs,
):
    updater_pipeline = AuthenticationRepositoryUpdatePipeline(
        operation,
        url,
        auth_path,
        library_dir,
        update_from_filesystem,
        expected_repo_type,
        target_repo_classes,
        target_factory,
        only_validate,
        validate_from_commit,
        conf_directory_root,
        out_of_band_authentication,
        checkout,
        excluded_target_globs,
    )
    updater_pipeline.run()
    output = updater_pipeline.output
    return (
        output.event,
        output.users_auth_repo,
        output.auth_repo_name,
        output.commits_data,
        output.error,
        output.targets_data,
    )


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
):
    settings.strict = strict

    auth_path = Path(auth_path).resolve()

    if library_dir is None:
        library_dir = auth_path.parent.parent
    else:
        library_dir = Path(library_dir).resolve()

    expected_repo_type = (
        UpdateType.TEST
        if (auth_path / "targets" / "test-auth-repo").exists()
        else UpdateType.OFFICIAL
    )
    settings.overwrite_last_validated_commit = True
    settings.last_validated_commit = validate_from_commit
    try:

        auth_repo_name, error = _update_named_repository(
            operation=OperationType.UPDATE,
            url=str(auth_path),
            auth_path=str(auth_path),
            library_dir=library_dir,
            update_from_filesystem=True,
            expected_repo_type=expected_repo_type,
            only_validate=True,
            validate_from_commit=validate_from_commit,
            excluded_target_globs=excluded_target_globs,
        )
        if error:
            raise error
    except Exception as e:
        raise ValidationFailedError(
            f"Validation or repository {auth_repo_name} failed due to error: {e}"
        )
    settings.overwrite_last_validated_commit = False
    settings.last_validated_commit = None
