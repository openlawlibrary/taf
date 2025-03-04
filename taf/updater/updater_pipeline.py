from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from enum import Enum
import functools
from pathlib import Path
import re
import shutil
from typing import Any, Dict, List, Optional

from attr import attrs, define, field

from taf.git import GitError
from taf.git import GitRepository
from taf.constants import INFO_JSON_PATH

from taf.models.types import Commitish
import taf.settings as settings
import taf.repositoriesdb as repositoriesdb
from taf.auth_repo import AuthenticationRepository
from taf.exceptions import (
    MissingInfoJsonError,
    UpdateFailedError,
    MultipleRepositoriesNotCleanError,
)
from taf.updater.handlers import GitUpdater
from taf.updater.lifecycle_handlers import Event
from taf.updater.types.update import OperationType, UpdateType
from taf.utils import TempPartition, on_rm_error, ensure_pre_push_hook
from tuf.ngclient.updater import Updater
from taf.log import taf_logger

EXPIRED_METADATA_ERROR = "ExpiredMetadataError"


class UpdateStatus(Enum):
    SUCCESS = 1
    PARTIAL = 2
    FAILED = 3


class RunMode(Enum):
    UPDATE = 1
    LOCAL_VALIDATION = 2
    ALL = 3


@define
class UpdateState:
    """
    A class to manage the state of repository updates, encapsulating information about authentication and validation
    of commits, and the management of repository data during updates.

    Attributes:
        auth_commits_since_last_validated (List[Any]): A list of fetched commits following the last validated commit
        invalid_auth_commits (List[Any]): List of authenticated commits identified as invalid.
        existing_repo (bool): Indicates if the repository already exists.
        is_test_repo (bool): Flags the repository as a test repository. Is set based on the existance of a specific target file.
        update_status (UpdateStatus): Update status - successful, partial, failed
        update_successful (bool): Indicates whether the update was successful.
        event (Event): event to be passed into the lifecycle handlers following the update.
        users_auth_repo (Optional["AuthenticationRepository"]): User's authentication repository.
        validation_auth_repo (Optional["AuthenticationRepository"]): Temporary authentication repository used for validation.
        auth_repo_name (Optional[str]): Name of the authentication repository.
        errors (Optional[List[Exception]]): Errors encountered during the update process.
        warnings (Optional[List[Exception]]): Warnings issued during the update process.
        targets_data (Dict[str, Any]): Data related to the target repositories, set based on the information in the
            authentication repository.
        last_validated_commit (str): The commit SHA of the last validated commit across the entire set of repositories.
            This is only updated if the update is run without the --exclude-target option, so if the auth repo and all
            target repositories were updated.
        last_validated_data (Dict[str, Any]): Data set after each partial or successful update. If run with
            --exclude-targets, last validated commit is set for each updated repo.
        temp_target_repositories (Dict[str, "GitRepository"]): Temporary repositories created and cleaned up during
            the update process.
        users_target_repositories (Dict[str, "GitRepository"]): Permanent repositories within the user's local directory.
        repos_on_disk (Dict[str, "GitRepository"]): Repositories that are already present in the user's local directory
            at the start of the update.
        repos_not_on_disk (Dict[str, "GitRepository"]): Repositories not present in the user's local directory at the
            start of the update.
        target_branches_data_from_auth_repo (Dict): Target repositories data, sorted by branches, based on information
            from the authentication repository.
        targets_data_by_auth_commits (Dict): Targets data organized by authentication commits.
        old_heads_per_target_repos_branches (Dict[str, Dict[str, str]]): Old head commits per target repository branches.
        fetched_commits_per_target_repos_branches (Dict[str, Dict[str, List[str]]]): Fetched commits per target repository branches.
        validated_commits_per_target_repos_branches (Dict[str, Dict[str, str]]): Validated commits per target repository branches.
        additional_commits_per_target_repos_branches (Dict[str, Dict[str, List[str]]]): Additional commits per target repository branches.
        validated_auth_commits (List[str]): List of validated authenticated commits.
        temp_root (TempPartition): Temporary storage partition used during updates.
        update_handler (GitUpdater): update handler used to interface with TUF's updater.
        clean_check_data (Dict[str, str]): A dictionary used while checking if the repositories are clean.
        last_validated_data_per_repositories (Dict[str, Dict[str, str]]): Keeps track of last successfully validated
            commits per branches of target repositories. Updated during the validation process.
        all_targets_auth_commits (List[str]): All commits of the authentication repository that correspond
            to commits of target repositories that need to be validated. If the previous update excluded some
            target repositories, this list will not be the same as the list containing new auth repo commits.
        is_partially_updated (bool): Indicates if the update was partial.
    """

    auth_commits_since_last_validated: List[Any] = field(factory=list)
    invalid_auth_commits: List[Any] = field(factory=list)
    existing_repo: bool = field(default=False)
    is_test_repo: bool = field(default=False)
    update_status: UpdateStatus = field(default=None)
    update_successful: bool = field(default=False)
    event: Optional[str] = field(default=None)
    users_auth_repo: Optional["AuthenticationRepository"] = field(default=None)
    validation_auth_repo: Optional["AuthenticationRepository"] = field(default=None)
    auth_repo_name: Optional[str] = field(default=None)
    errors: Optional[List[Exception]] = field(default=None)
    warnings: Optional[List[Exception]] = field(default=None)
    targets_data: Dict[str, Any] = field(factory=dict)
    last_validated_commit: Commitish = field(factory=str)
    last_validated_data: str = field(factory=dict)
    temp_target_repositories: Dict[str, "GitRepository"] = field(factory=dict)
    users_target_repositories: Dict[str, "GitRepository"] = field(factory=dict)
    repos_on_disk: Dict[str, GitRepository] = field(factory=dict)
    repos_not_on_disk: Dict[str, GitRepository] = field(factory=dict)
    target_branches_data_from_auth_repo: Dict = field(factory=dict)
    targets_data_by_auth_commits: Dict = field(factory=dict)
    old_heads_per_target_repos_branches: Dict[str, Dict[str, str]] = field(factory=dict)
    fetched_commits_per_target_repos_branches: Dict[
        str, Dict[str, List[Commitish]]
    ] = field(factory=dict)
    validated_commits_per_target_repos_branches: Dict[
        str, Dict[str, Commitish]
    ] = field(factory=dict)
    additional_commits_per_target_repos_branches: Dict[
        str, Dict[str, List[Commitish]]
    ] = field(factory=dict)
    validated_auth_commits: List[Commitish] = field(factory=list)
    temp_root: TempPartition = field(default=None)
    update_handler: GitUpdater = field(default=None)
    clean_check_data: Dict[str, str] = field(factory=dict)
    last_validated_data_per_repositories: Dict[str, Dict[str, str]] = field(
        factory=dict
    )
    all_targets_auth_commits: List[Commitish] = field(factory=list)
    is_partially_updated: bool = field(default=False)


@attrs
class AuthCommitsData:
    """
    Data class for storing commit data information for update output
    """

    # Commit hash for the commit of the auth repo before update
    before_pull: Optional[str] = field(default=None)
    # Last commit hash of the updated auth repo after update
    # Note: it could be the same as the before_pull if no new commits were fetched
    after_pull: Optional[str] = field(default=None)
    # List of commit hashes for all commits that are newer than the last validated commit after update
    new: Optional[List[str]] = field(default=list)


@attrs
class UpdateOutput:
    event: str = field()
    users_auth_repo: Optional[Any] = field(default=None)
    auth_repo_name: Optional[str] = field(default=None)
    commits_data: AuthCommitsData = field(factory=AuthCommitsData)
    error: Optional[Exception] = field(default=None)
    targets_data: Dict[str, Any] = field(factory=dict)
    warnings: Optional[str] = field(default=None)


def cleanup_decorator(pipeline_function):
    @functools.wraps(pipeline_function)
    def wrapper(self, *args, **kwargs):
        try:
            result = pipeline_function(self, *args, **kwargs)
            return result
        finally:
            if (
                not self.only_validate
                and self.state.event == Event.FAILED
                and not self.state.existing_repo
                and self.state.users_auth_repo is not None
            ):
                shutil.rmtree(self.state.users_auth_repo.path, onerror=on_rm_error)
                shutil.rmtree(self.state.users_auth_repo.conf_dir)

    return wrapper


def combine_statuses(current_status, new_status):
    """
    Combine the current overall status with the new step status.
    """
    if current_status is None:
        return new_status
    if new_status == UpdateStatus.FAILED:
        return UpdateStatus.FAILED
    elif new_status == UpdateStatus.PARTIAL:
        if current_status != UpdateStatus.FAILED:
            return UpdateStatus.PARTIAL
    return current_status


def format_commit(commit: Commitish):
    return Commitish.from_hash(hash=commit.hash[:10])


class Pipeline:
    def __init__(self, steps, run_mode):
        self.state = None
        self.steps = steps
        self.current_step = None
        self.run_mode = run_mode

    def run(self):
        self.state.errors = []
        self.state.warnings = []
        for step, step_run_mode, should_run_fn in self.steps:
            try:
                if (
                    step_run_mode == RunMode.ALL or step_run_mode == self.run_mode
                ) and (
                    should_run_fn()
                ):  # runs method like object
                    self.current_step = step
                    update_status = step()
                    combined_status = combine_statuses(
                        self.state.update_status, update_status
                    )
                    self.state.update_status = combined_status
                    if combined_status == UpdateStatus.FAILED:
                        message = "\n".join(str(error) for error in self.state.errors)
                        raise UpdateFailedError(message)

            except Exception as e:
                self.handle_error(e)
                break
            except KeyboardInterrupt as e:
                self.handle_error(e)
        self.set_output()

    def handle_error(self, e):
        self.remove_temp_repositories()
        self.state.event = Event.FAILED
        if self.state.auth_repo_name is not None:
            taf_logger.error(
                "An error occurred while updating repository {} while running step {}: {}",
                self.state.auth_repo_name,
                self.current_step.__name__,
                str(e),
            )
        else:
            taf_logger.error(
                "An error occurred while updating authentication repository while running step {}: {}",
                self.current_step.__name__,
                str(e),
            )

    def set_output(self):
        pass


class AuthenticationRepositoryUpdatePipeline(Pipeline):
    def __init__(
        self,
        update_config,
    ):

        super().__init__(
            steps=[
                (
                    self.start_update,
                    RunMode.ALL,
                    self.should_run_step_default,
                ),
                (
                    self.set_users_auth_repo,
                    RunMode.ALL,
                    self.should_run_step_default,
                ),
                (
                    self.set_existing_target_repositories,
                    RunMode.UPDATE,
                    self.should_run_step_default,
                ),  # specify extra method here and runner will call to check if we can have it here
                (
                    self.check_if_local_repositories_clean,
                    RunMode.UPDATE,
                    self.should_run_step_default,
                ),  # run only when want to updatae; valaidation doesn't change repop sstate; merge will fail without this
                (
                    self.clone_auth_to_temp,
                    RunMode.ALL,
                    self.should_update_auth_repos,
                ),  # should be done regardless of flags
                (
                    self.prepare_for_auth_update_and_check_last_validated_commit,
                    RunMode.ALL,
                    self.should_update_auth_repos,
                ),
                (
                    self.run_tuf_updater,
                    RunMode.ALL,
                    self.should_update_auth_repos,
                ),  # should be done regardless of flags
                (
                    self.validate_out_of_band_and_update_type,
                    RunMode.ALL,
                    self.should_update_auth_repos,
                ),  # auth repo
                (
                    self.validate_last_validated_commit,
                    RunMode.ALL,
                    self.should_update_auth_repos,
                ),
                (
                    self.clone_or_fetch_users_auth_repo,
                    RunMode.UPDATE,
                    self.should_update_auth_repos,
                ),  # auth repo
                # should_validate_target_repos
                (
                    self.load_target_repositories,
                    RunMode.ALL,
                    self.should_run_step_default,
                ),
                (
                    self.check_if_previous_update_partial,
                    RunMode.ALL,
                    self.should_run_step_default,
                ),
                (
                    self.set_auth_commit_for_target_repos,
                    RunMode.ALL,
                    self.should_validate_target_repos,
                ),
                (
                    self.check_if_repositories_on_disk,
                    RunMode.LOCAL_VALIDATION,
                    self.should_validate_target_repos,
                ),
                (
                    self.clone_target_repositories_to_temp,
                    RunMode.UPDATE,
                    self.should_validate_target_repos,
                ),
                (
                    self.determine_start_commits,
                    RunMode.ALL,
                    self.should_validate_target_repos,
                ),
                (
                    self.get_targets_data_from_auth_repo,
                    RunMode.ALL,
                    self.should_validate_target_repos,
                ),
                (
                    self.check_if_local_target_repositories_clean,
                    RunMode.UPDATE,
                    self.should_validate_target_repos,
                ),
                (
                    self.get_target_repositories_commits,
                    RunMode.ALL,
                    self.should_validate_target_repos,
                ),
                (
                    self.validate_target_repositories,
                    RunMode.ALL,
                    self.should_validate_target_repos,
                ),
                (
                    self.validate_and_set_additional_commits_of_target_repositories,
                    RunMode.ALL,
                    self.should_validate_target_repos,
                ),
                (
                    self.update_users_target_repositories,
                    RunMode.UPDATE,
                    self.should_validate_target_repos,
                ),  # fetch commits; END UPDATE TARGET REPOS
                (
                    self.merge_commits,
                    RunMode.UPDATE,
                    self.should_validate_target_repos,
                ),  # merge fetched commits
                (
                    self.merge_auth_commits,
                    RunMode.UPDATE,
                    self.should_run_step_default,
                ),  # merge fetched commits
                (
                    self.remove_temp_repositories,
                    RunMode.UPDATE,
                    self.should_run_step_default,
                ),  # only removes auth repo with --no-targets
                (
                    self.set_target_repositories_data,
                    RunMode.UPDATE,
                    self.should_validate_target_repos,
                ),  # skipped with no-targets
                (
                    self.print_additional_commits,
                    RunMode.ALL,
                    self.should_validate_target_repos,
                ),  # skipped with no-targets; prints all other commits that exist but are not merged
                (self.check_pre_push_hook, RunMode.ALL, self.should_update_auth_repos),
                (self.finish_update, RunMode.ALL, self.should_run_step_default),
            ],
            run_mode=(
                RunMode.LOCAL_VALIDATION
                if update_config.only_validate
                else RunMode.UPDATE
            ),
        )
        self.operation = update_config.operation
        self.urls = update_config.clone_urls or [update_config.remote_url]
        self.library_dir = update_config.library_dir
        self.auth_path = update_config.path
        self.update_from_filesystem = update_config.update_from_filesystem
        self.expected_repo_type = update_config.expected_repo_type
        self.target_repo_classes = update_config.target_repo_classes
        self.target_factory = update_config.target_factory
        self.only_validate = update_config.only_validate
        self.validate_from_commit = Commitish.from_hash(
            update_config.validate_from_commit
        )
        self.out_of_band_authentication = Commitish.from_hash(
            update_config.out_of_band_authentication
        )
        self.checkout = update_config.checkout
        self.bare = update_config.bare
        self.excluded_target_globs = update_config.excluded_target_globs
        self.no_targets = update_config.no_targets
        self.no_upstream = update_config.no_upstream
        self.force = update_config.force
        self.state = UpdateState()
        self.state.targets_data = {}
        self._output = None

    @property
    def output(self):
        if not self._output:
            raise ValueError(
                "Pipeline has not been run yet. Please run the pipeline first."
            )
        return self._output

    def should_run_step_default(self):
        return True

    def should_update_auth_repos(self):
        return True

    def should_validate_target_repos(self):
        if self.no_targets:
            return False
        if self.no_upstream:
            # check if self.state.event has changed.
            # if changed, validate the target repos
            if self.state.event == Event.CHANGED or self.state.event == Event.PARTIAL:
                return True
            return self.state.is_partially_updated
        return True

    def start_update(self):
        # This message should be shown regardless of verbosity setting
        update_text = "validation" if self.only_validate else "update"
        if self.auth_path:
            auth_repo_name = GitRepository(path=self.auth_path).name
            taf_logger.log("NOTICE", f"{auth_repo_name}: Starting {update_text}...")
        else:
            taf_logger.log("NOTICE", f"Starting {update_text}...")

    def finish_update(self):
        # This message should be shown regardless of verbosity setting
        update_text = "validation" if self.only_validate else "update"
        taf_logger.log(
            "NOTICE", f"{self.state.auth_repo_name}: Finished {update_text}!"
        )

    def set_users_auth_repo(self):
        settings.update_from_filesystem = self.update_from_filesystem
        self.state.existing_repo = False
        if self.auth_path:
            self.state.users_auth_repo = AuthenticationRepository(
                path=self.auth_path, urls=self.urls
            )
            self.state.auth_repo_name = self.state.users_auth_repo.name
            if self.state.users_auth_repo.is_git_repository_root:
                self.state.existing_repo = True

    def set_existing_target_repositories(self):
        taf_logger.debug(
            f"{self.state.auth_repo_name}: Checking which repositories are already on disk..."
        )
        self.state.repos_on_disk = {}
        if self.state.users_auth_repo is not None:
            if self.state.users_auth_repo.is_git_repository_root:
                # load target repositories in order to check if they are clean or synced
                # after updating the authentication repotiory, we need to load them again
                # since repositories.json could've changed
                repositoriesdb.load_repositories(
                    self.state.users_auth_repo,
                    library_dir=self.library_dir,
                    only_load_targets=True,
                    excluded_target_globs=self.excluded_target_globs,
                    raise_error_if_no_urls=True,
                )
                target_repositories = repositoriesdb.get_deduplicated_repositories(
                    self.state.users_auth_repo,
                    excluded_target_globs=self.excluded_target_globs,
                    raise_error_if_no_urls=True,
                )
                self.state.repos_on_disk = {
                    target_repo.name: target_repo
                    for target_repo in target_repositories.values()
                    if target_repo.is_git_repository_root
                }
                repositoriesdb.clear_repositories_db()
        return UpdateStatus.SUCCESS

    def _get_last_validated_commit(self, repo_name) -> Commitish:
        if repo_name in self.state.last_validated_data:
            return Commitish.from_hash(self.state.last_validated_data[repo_name])
        return self.state.last_validated_commit

    def _set_last_validated_commit(self):
        if self.operation == OperationType.CLONE:
            settings.last_validated_commit[self.state.validation_auth_repo.name] = None
            self.state.last_validated_commit = None
            self.state.last_validated_data = {}
        elif not self.validate_from_commit:
            users_auth_repo = AuthenticationRepository(path=self.auth_path)
            # last_validated_commit is not updated after a partial update
            # however, last_validated_data file is
            # even thought we cannot claim that the system as a whole is valid
            # after a partial update, there is no need to validate the auth repo
            # from an older commit, just because one of more targets were skipped
            self.state.last_validated_data = users_auth_repo.last_validated_data
            last_validated_commit = self.state.last_validated_data.get(
                users_auth_repo.name
            )

            settings.last_validated_commit[
                self.state.validation_auth_repo.name
            ] = last_validated_commit
            self.state.last_validated_commit = Commitish.from_hash(
                last_validated_commit
            )
        elif self.validate_from_commit:
            settings.last_validated_commit[
                self.state.validation_auth_repo.name
            ] = self.validate_from_commit
            self.state.last_validated_commit = self.validate_from_commit

    def check_if_local_repositories_clean(self):
        try:
            self.state.clean_check_data = {}
            # Early exit if the repository does not exist
            if not self.state.existing_repo:
                return UpdateStatus.SUCCESS

            auth_repo = AuthenticationRepository(path=self.auth_path, urls=self.urls)
            taf_logger.info(
                f"{auth_repo.name}: Checking if local repositories are clean..."
            )

            dirty_index_repos = []
            unpushed_commits_repos_and_branches = []

            if auth_repo.is_bare_repository:
                taf_logger.info(
                    f"Skipping clean check for bare repository {auth_repo.name}"
                )
                return UpdateStatus.SUCCESS

            if auth_repo.something_to_commit():
                if self.force:
                    taf_logger.info(
                        f"Resetting repository {auth_repo.name} to clean state for a forced update."
                    )
                    auth_repo.clean_and_reset()
                else:
                    taf_logger.error(
                        f"Repository {auth_repo.name} not clean. Use --force to force update."
                    )
                    dirty_index_repos.append(auth_repo.name)

            contains_unpushed, unpushed_commits = auth_repo.branch_unpushed_commits(
                auth_repo.default_branch
            )
            if contains_unpushed:
                if self.force and len(unpushed_commits):
                    taf_logger.info(
                        f"Resetting repository {auth_repo.name} to clean state for a forced update."
                    )
                    _remove_unpushed_commits(
                        auth_repo, auth_repo.default_branch, unpushed_commits
                    )

                else:
                    unpushed_commits_repos_and_branches.append(
                        (auth_repo.name, auth_repo.default_branch)
                    )

            branches_per_repos = {}
            for target_name, target_repo in self.state.repos_on_disk.items():
                target = auth_repo.get_target(target_name)
                if target and "branch" in target:
                    branches_per_repos.setdefault(target_name, []).append(
                        target["branch"]
                    )
            target_dirty, target_unpushed = self._check_if_target_repos_clean(
                self.state.repos_on_disk.values(), branches_per_repos
            )
            dirty_index_repos.extend(target_dirty)
            unpushed_commits_repos_and_branches.extend(target_unpushed)

            if (
                len(dirty_index_repos) > 0
                or len(unpushed_commits_repos_and_branches) > 0
            ):
                raise MultipleRepositoriesNotCleanError(
                    dirty_index_repos, unpushed_commits_repos_and_branches
                )
            return UpdateStatus.SUCCESS
        except Exception as e:
            self.state.errors.append(e)
            self.state.event = Event.FAILED
            return UpdateStatus.FAILED

    def check_if_previous_update_partial(self):
        """
        Check if the previous update was a partial update
        """

        def _previous_update_partial():
            if not self.state.users_auth_repo.last_validated_commit:
                return True

            # validate from last_validated_commit if last_validated_data does not exist
            # (if last_validated_data was deleted)
            if not self.state.users_auth_repo.last_validated_data:
                return True
            if (
                self.state.users_auth_repo.last_validated_commit
                != self.state.users_auth_repo.last_validated_data.get(
                    self.state.users_auth_repo.name
                )
            ):
                return True

            last_validated_commits = set()
            for repo_name in self.state.users_target_repositories:
                if self.state.users_auth_repo.last_validated_data:
                    if repo_name not in self.state.users_auth_repo.last_validated_data:
                        return True
                    last_validated_commits.add(
                        self.state.users_auth_repo.last_validated_data[repo_name]
                    )
            return len(last_validated_commits) > 1

        self.state.is_partially_updated = _previous_update_partial()

    def _check_if_target_repos_clean(self, target_repos, branches_per_repo):
        dirty_index_repos = []
        unpushed_commits_repos_and_branches = []
        # Check the target repositories on disk
        for repository in target_repos:
            if repository.is_bare_repository:
                taf_logger.info(
                    f"Skipping clean check for bare repository {repository.name}"
                )
                continue

            if (
                repository.name not in self.state.clean_check_data
                and repository.something_to_commit()
            ):
                if self.force:
                    taf_logger.info(
                        f"Resetting repository {repository.name} to clean state for a forced update."
                    )
                    repository.clean_and_reset()
                else:
                    dirty_index_repos.append(repository.name)

            if repository not in self.state.clean_check_data:
                self.state.clean_check_data[repository.name] = []
            for branch in branches_per_repo[repository.name]:
                (
                    contains_unpushed,
                    unpushed_commits,
                ) = repository.branch_unpushed_commits(branch)
                self.state.clean_check_data[repository.name].append(branch)
                if contains_unpushed:
                    if self.force and len(unpushed_commits):
                        taf_logger.info(
                            f"Resetting repository {repository.name} to clean state for a forced update."
                        )
                        _remove_unpushed_commits(repository, branch, unpushed_commits)
                    else:
                        unpushed_commits_repos_and_branches.append(
                            (repository.name, branch)
                        )
        return dirty_index_repos, unpushed_commits_repos_and_branches

    @cleanup_decorator
    def clone_auth_to_temp(self):
        try:
            users_path = self.auth_path or self.library_dir
            self.state.temp_root = TempPartition(Path(users_path))

            if self.auth_path:
                auth_repo_name = GitRepository(path=self.auth_path).name
                taf_logger.info(f"{auth_repo_name}: Cloning auth repository to temp...")
            else:
                taf_logger.info("Cloning auth repository to temp...")

            path = Path(self.state.temp_root.temp_dir, "auth_repo").absolute()
            self.state.validation_auth_repo = AuthenticationRepository(
                path=path, urls=self.urls, alias="Validation repository"
            )
            self.state.validation_auth_repo.clone(bare=True)
            self.state.validation_auth_repo.fetch(fetch_all=True)

            settings.validation_repo_path[
                self.state.validation_auth_repo.name
            ] = self.state.validation_auth_repo.path
        except Exception as e:
            self.state.errors.append(e)
            self.state.event = Event.FAILED
            return UpdateStatus.FAILED

    def prepare_for_auth_update_and_check_last_validated_commit(self):
        try:
            if self.operation == OperationType.CLONE_OR_UPDATE:
                if (
                    self.auth_path is not None
                    and AuthenticationRepository(
                        path=self.auth_path
                    ).is_git_repository_root
                ):
                    self.operation = OperationType.UPDATE
                else:
                    self.operation = OperationType.CLONE

            def _clear_lvc():
                settings.last_validated_commit[
                    self.state.validation_auth_repo.name
                ] = None
                self.state.last_validated_commit = None

            self.state.auth_commits_since_last_validated = None
            # set last validated commit before running the updater
            # this last validated commit is read from the settings
            self._set_last_validated_commit()

            # check if auth path is provided and if that is not the case
            # check if info.json exists. info.json will be read after validation
            # at revision determined by the last validated commit
            # but we do not want the user to have to wait for the validation to be over
            # before raising an error because info.json is missing
            top_commit_of_validation_repo = (
                self.state.validation_auth_repo.top_commit_of_branch(
                    self.state.validation_auth_repo.default_branch
                )
            )
            if not self.auth_path:
                self.state.auth_repo_name = (
                    _get_repository_name_raise_error_if_not_defined(
                        self.state.validation_auth_repo, top_commit_of_validation_repo
                    )
                )
                self.auth_path = Path(self.library_dir, self.state.auth_repo_name)

            if (
                self.state.users_auth_repo
                and self.state.users_auth_repo.is_git_repository_root
            ):
                # validate the top commit of the user's auth repo
                # if it's not in the remote repo -> fail early
                default_branch = self.state.validation_auth_repo.default_branch
                users_head_commit = self.state.users_auth_repo.top_commit_of_branch(
                    default_branch
                )
                if not _check_if_commit_on_branch(
                    self.state.validation_auth_repo, users_head_commit, default_branch
                ):
                    error_msg = (
                        f"The newest commit of repository {self.state.users_auth_repo.name} is no longer "
                        f"on branch {default_branch} of the remote repository. This could "
                        "either mean that    there was an unauthorized push to the remote "
                        "or an invalid modification of the local repository."
                    )
                    # this is always an error, force or no force
                    raise UpdateFailedError(error_msg)

                if self.state.last_validated_commit:
                    # validate before running the updater
                    # if the last validated commit is not contained by the remote repository
                    # either the remote repository was tempered with or the last validated commit
                    # was manually set to an invalid value
                    if (
                        self.state.last_validated_commit
                        and not _check_if_commit_on_branch(
                            self.state.validation_auth_repo,
                            self.state.last_validated_commit,
                            default_branch,
                        )
                    ):
                        error_msg = (
                            f"Last validated commit {self.state.last_validated_commit} is no longer on {default_branch} "
                            f"of the remote {self.state.users_auth_repo.name} repository. This could "
                            "either mean that there was an unauthorized push to the remote "
                            "repository, or that last_validated_commit file was modified. "
                        )
                        if self.force:
                            # if last validated commit is not in the remote and run with --force, start the
                            # validation from the beginning. This will set the last validated commit
                            taf_logger.warning(
                                f"{error_msg}. Starting validation from the first commit"
                            )
                            _clear_lvc()
                        else:
                            raise UpdateFailedError(
                                f"{error_msg}\nRun the updater with the --force flag to run the validation from the first commit"
                            )

                    if (
                        self.state.last_validated_commit
                        and users_head_commit != self.state.last_validated_commit
                    ):
                        if not _check_if_commit_on_branch(
                            self.state.users_auth_repo,
                            self.state.last_validated_commit,
                            default_branch,
                            include_remotes=True,
                        ):
                            if self.force:
                                _clear_lvc()
                                taf_logger.warning(
                                    f"{self.state.users_auth_repo.name}: Last validated commit {users_head_commit} is not in repository {self.state.users_auth_repo.name} "
                                    "Running the validation from the first commit."
                                )
                            else:
                                raise UpdateFailedError(
                                    f"{self.state.users_auth_repo.name}: Last validated commit {users_head_commit} is not in repository {self.state.users_auth_repo.name} "
                                    "\nRun the updater with the --force flag to run the validation from the first commit"
                                )
                        else:
                            commits_since = (
                                self.state.users_auth_repo.all_commits_since_commit(
                                    since_commit=self.state.last_validated_commit,
                                    branch=default_branch,
                                )
                            )
                            # if the user's head sha is newer than last validated commit
                            # that can mean that the changes were pulled manually
                            # validation will start from the last validated commit
                            # and there is no need to do anything else
                            # if the user's head commit is not newer or equal to the last validated commit
                            # that could meant that the user manually removed some commits from the local
                            # repository
                            if users_head_commit not in commits_since:
                                if self.force:
                                    _clear_lvc()
                                    taf_logger.warning(
                                        f"{self.state.users_auth_repo.name}: Top commit of repository {self.state.users_auth_repo.name} {users_head_commit} is not equal to or newer than the last successful commit. "
                                        "Running the validation from the first commit."
                                    )
                                else:
                                    raise UpdateFailedError(
                                        f"Top commit of repository {self.state.users_auth_repo.name} {users_head_commit} is not equal to or newer than the last successful commit. "
                                        "\nRun the updater with the --force flag to run the validation from the first commit"
                                    )

        except Exception as e:
            self.state.errors.append(e)
            self.state.event = Event.FAILED
            return UpdateStatus.FAILED

    def run_tuf_updater(self):

        try:

            self.state.update_handler = GitUpdater(
                self.urls, self.library_dir, self.state.validation_auth_repo.name
            )
            last_validated_remote_commit, error = _run_tuf_updater(
                self.state.update_handler, self.state.auth_repo_name
            )
            if last_validated_remote_commit is None and error is not None:
                raise error

            # having validated the repository, read info.json from the last
            # valid commit if it is not the same as the most recent commit
            top_commit_of_validation_repo = (
                self.state.validation_auth_repo.top_commit_of_branch(
                    self.state.validation_auth_repo.default_branch
                )
            )
            if not self.auth_path:
                if top_commit_of_validation_repo != last_validated_remote_commit:
                    self.state.auth_repo_name = (
                        _get_repository_name_raise_error_if_not_defined(
                            self.state.validation_auth_repo,
                            last_validated_remote_commit,
                        )
                    )

            if (
                self.state.users_auth_repo is None
                or self.state.users_auth_repo.name != self.state.auth_repo_name
            ):
                self.state.users_auth_repo = AuthenticationRepository(
                    library_dir=self.library_dir,
                    name=self.state.auth_repo_name,
                    urls=self.urls,
                )

            self._validate_operation_type()

            self.state.is_test_repo = self.state.validation_auth_repo.is_test_repo

            self.state.invalid_auth_commits = []
            if error is None:
                self.state.auth_commits_since_last_validated = list(
                    self.state.update_handler.commits
                )
                taf_logger.info(
                    "Successfully validated authentication repository {}",
                    self.state.auth_repo_name,
                )
                self.state.event = (
                    Event.CHANGED
                    if len(self.state.auth_commits_since_last_validated) > 1
                    or (
                        self.operation == OperationType.CLONE
                        and len(self.state.auth_commits_since_last_validated) == 1
                    )
                    else Event.UNCHANGED
                )
                return UpdateStatus.SUCCESS
            else:
                try:
                    last_validated_index = self.state.update_handler.commits.index(
                        last_validated_remote_commit
                    )
                except ValueError:
                    last_validated_index = -1

                if last_validated_index != -1:
                    self.state.auth_commits_since_last_validated = (
                        self.state.update_handler.commits[: last_validated_index + 1]
                    )
                    self.state.invalid_auth_commits = self.state.update_handler.commits[
                        last_validated_index + 1 :
                    ]
                else:
                    self.state.auth_commits_since_last_validated = []
                    self.state.invalid_auth_commits = self.state.update_handler.commits[
                        :
                    ]
                self.state.errors.append(error)
                self.state.event = Event.PARTIAL
                return UpdateStatus.PARTIAL

        except Exception as e:
            self.state.errors.append(e)
            self.state.event = Event.FAILED
            return UpdateStatus.FAILED
        finally:
            # always clean up repository updater
            if (
                self.state.users_auth_repo is None
                and self.state.auth_repo_name is not None
            ):
                self.state.users_auth_repo = AuthenticationRepository(
                    self.library_dir,
                    self.state.auth_repo_name,
                    urls=self.urls,
                )

    def _validate_operation_type(self):
        if self.operation == OperationType.CLONE and self.state.existing_repo:
            raise UpdateFailedError(
                f"Destination path {self.state.users_auth_repo.path} already exists and is not an empty directory. Run 'taf repo update' to update it."
            )
        elif self.operation == OperationType.UPDATE and not self.state.existing_repo:
            raise UpdateFailedError(
                f"{self.state.users_auth_repo.path} is not a Git repository. Run 'taf repo clone' instead"
            )

    def validate_out_of_band_and_update_type(self):
        # this is the repository cloned inside the temp directory
        # we validate it before updating the actual authentication repository
        taf_logger.info(
            f"{self.state.auth_repo_name}: Validating out of band commit and update type..."
        )
        try:
            if (
                self.out_of_band_authentication is not None
                and self.state.users_auth_repo.last_validated_commit is None
                and self.state.auth_commits_since_last_validated[0]
                != self.out_of_band_authentication
            ):
                raise UpdateFailedError(
                    f"First commit of repository {self.state.auth_repo_name} does not match "
                    "out of band authentication commit"
                )

            if self.expected_repo_type != UpdateType.EITHER:
                # check if the repository being updated is a test repository
                if (
                    self.state.is_test_repo
                    and self.expected_repo_type != UpdateType.TEST
                ):
                    raise UpdateFailedError(
                        f"Repository {self.state.users_auth_repo.name} is a test repository. "
                        'Call update with "--expected-repo-type" test to update a test '
                        "repository"
                    )
                elif (
                    not self.state.is_test_repo
                    and self.expected_repo_type == UpdateType.TEST
                ):
                    raise UpdateFailedError(
                        f"Repository {self.state.users_auth_repo.name} is not a test repository,"
                        ' but update was called with the "--expected-repo-type" test'
                    )
        except Exception as e:
            self.state.errors.append(e)
            self.state.event = Event.FAILED
            return UpdateStatus.FAILED

    def validate_last_validated_commit(self):
        # last validated commit was already validated against the remote repo before the update was initiated
        # so just check if it was manually set to a commit that follows the last valid commit
        if (
            self.state.last_validated_commit is not None
            and self.state.last_validated_commit in self.state.invalid_auth_commits
        ):
            error_msg = f"Last validated commit {self.state.last_validated_commit} could not be validated."
            if self.force:
                # if last validated commit is not in the remote and run with --force, start the
                # validation from the beginning. This will set the last validated commit
                taf_logger.warning(
                    f"{error_msg}. Starting validation from the first commit"
                )
                self.state.last_validated_commit = None
            else:
                raise UpdateFailedError(error_msg)

    def clone_or_fetch_users_auth_repo(self):
        # fetch the latest commit or clone the repository without checkout
        # do not merge before targets are validated as well
        taf_logger.info(
            f"{self.state.auth_repo_name}: Cloning or updating user's authentication repository..."
        )
        try:
            if self.state.existing_repo:
                self.state.users_auth_repo.fetch(fetch_all=True)
            else:
                self.state.users_auth_repo.clone(bare=self.bare)
        except Exception as e:
            self.state.errors.append(e)
            self.state.event = Event.FAILED
            return UpdateStatus.FAILED
        return UpdateStatus.SUCCESS

    def set_auth_commit_for_target_repos(self):
        last_commits_per_repos = {
            repo_name: self._get_last_validated_commit(repo_name)
            for repo_name in self.state.users_target_repositories
        }
        last_commits_per_repos[
            self.state.users_auth_repo.name
        ] = self._get_last_validated_commit(self.state.users_auth_repo.name)

        last_validated_commits = list(set(last_commits_per_repos.values()))

        if len(last_validated_commits) > 1:
            # not all target repositories were updated at the same time
            # updater was run with --exclude-targets
            # check if the repositories are in sync according to that data
            partially_validated_commits = (
                self.state.users_auth_repo.auth_repo_commits_after_repos_last_validated(
                    self.state.users_target_repositories.values(),
                    self.state.last_validated_data,
                )
            )
            all_auth_commits = partially_validated_commits
            for commit in self.state.auth_commits_since_last_validated:
                if commit not in all_auth_commits:
                    all_auth_commits.append(commit)
        else:
            all_auth_commits = self.state.auth_commits_since_last_validated

        self.state.all_targets_auth_commits = all_auth_commits

        self.state.targets_data_by_auth_commits = (
            self.state.users_auth_repo.targets_data_by_auth_commits(
                all_auth_commits,
                target_repos=self.state.users_target_repositories,
                last_commits_per_repos=last_commits_per_repos,
            )
        )

    def load_target_repositories(self):
        taf_logger.debug(f"{self.state.auth_repo_name}: Loading target repositories...")
        try:
            self.state.users_target_repositories = (
                repositoriesdb.get_deduplicated_repositories(
                    self.state.users_auth_repo,
                    self.state.auth_commits_since_last_validated[-1::],
                    excluded_target_globs=self.excluded_target_globs,
                    library_dir=self.library_dir,
                    raise_error_if_no_urls=not self.only_validate,
                )
            )
            if self.only_validate:
                self.state.temp_target_repositories = (
                    self.state.users_target_repositories
                )
            else:
                self.state.temp_target_repositories = {
                    repo.name: GitRepository(
                        self.state.temp_root.temp_dir,
                        repo.name,
                        urls=repo.urls,
                        custom=repo.custom,
                    )
                    for repo in self.state.users_target_repositories.values()
                }
                return UpdateStatus.SUCCESS
        except Exception as e:
            self.state.errors.append(e)
            self.state.event = Event.FAILED
            return UpdateStatus.FAILED

    def check_if_repositories_on_disk(self):
        taf_logger.info(
            f"{self.state.auth_repo_name}: Checking if all target repositories are already on disk..."
        )
        try:
            for repository in self.state.users_target_repositories.values():
                if not repository.is_git_repository_root:
                    is_git_repository = repository.is_git_repository_root
                    if not is_git_repository:
                        if self.only_validate:
                            self.state.targets_data = {}
                            msg = f"{repository.name} not on disk. Please run update to clone the repositories."
                            taf_logger.error(msg)
                            raise UpdateFailedError(msg)
            return UpdateStatus.SUCCESS
        except Exception as e:
            self.state.errors.append(e)
            self.state.event = Event.FAILED
            return UpdateStatus.FAILED

    def clone_target_repositories_to_temp(self):
        taf_logger.debug(
            f"{self.state.auth_repo_name}: Cloning target repositories to temp..."
        )
        try:

            self.state.repos_not_on_disk = {}
            self.state.repos_not_on_disk = {}

            def clone_repo_to_temp(temp_repo, users_repo):
                if users_repo.is_git_repository_root:
                    temp_repo.clone_from_disk(
                        users_repo.path,
                        users_repo.get_remote_url(),
                        is_bare=True,
                    )
                    self.state.repos_on_disk[users_repo.name] = users_repo
                else:
                    temp_repo.clone(bare=self.bare)
                    self.state.repos_not_on_disk[users_repo.name] = users_repo

            with ThreadPoolExecutor() as executor:
                futures = []
                for temp_repo in self.state.temp_target_repositories.values():
                    users_repo = self.state.users_target_repositories[temp_repo.name]
                    futures.append(
                        executor.submit(clone_repo_to_temp, temp_repo, users_repo)
                    )

                for future in as_completed(futures):
                    future.result()
            taf_logger.info(
                f"{self.state.auth_repo_name}: Finished cloning target repositories."
            )
            return UpdateStatus.SUCCESS
        except Exception as e:
            self.state.errors.append(e)
            self.state.event = Event.FAILED
            return UpdateStatus.FAILED

    def determine_start_commits(self):
        taf_logger.info(
            f"{self.state.auth_repo_name}: Validating initial state of target repositories..."
        )
        # if update was run with --exclude-target options, some target repositories might have been
        # validated up to an older commit, or never validated at all
        # that means that different repositories need to be validated from different start commits

        try:

            self.state.old_heads_per_target_repos_branches = defaultdict(dict)
            is_initial_state_in_sync = True
            # if last validated commit was not manually modified (set to a newer commit)
            # target repositories data that is extracted to them (commit and branch)
            # should be present in the local repository
            # if the local repository was manually modified (say, something was committed)
            # we still expect the last validated target commit to exist
            # and the remaining commits will be validated afterwards
            # if the last validated target commit does not exist, start the validation from scratch
            try:
                if self.state.last_validated_commit is not None:
                    for repository in self.state.temp_target_repositories.values():
                        if (
                            repository.name
                            not in self.state.targets_data_by_auth_commits
                        ):
                            continue

                        self.state.old_heads_per_target_repos_branches[
                            repository.name
                        ] = {}
                        repo_last_validated_commit = self._get_last_validated_commit(
                            repository.name
                        )
                        last_validated_repository_commits_data = (
                            self.state.targets_data_by_auth_commits[
                                repository.name
                            ].get(repo_last_validated_commit, {})
                        )

                        if last_validated_repository_commits_data:
                            if (
                                repository.name in self.state.repos_not_on_disk
                                and self._get_last_validated_commit(repository.name)
                                is not None
                            ):
                                is_initial_state_in_sync = False
                                break
                            if not self._is_repository_in_sync(
                                repository, last_validated_repository_commits_data
                            ):
                                is_initial_state_in_sync = False
                                break

                if not is_initial_state_in_sync:
                    taf_logger.log(
                        "NOTICE",
                        f"{self.state.users_auth_repo.name}: states of target repositories are not in sync with last validated commit. Starting the validation from the beginning",
                    )
            except Exception as e:
                taf_logger.log(
                    "NOTICE",
                    f"{self.state.users_auth_repo.name}: could not determine if repos are in sync due to error. Starting the validation from the beginning. Error: {e}",
                )
                is_initial_state_in_sync = False

            if not is_initial_state_in_sync:
                self._update_state_for_initial_sync()
                self.reset_target_repositories()

            return UpdateStatus.SUCCESS
        except Exception as e:
            self.state.errors.append(e)
            self.state.event = Event.FAILED
            return UpdateStatus.FAILED

    def _is_repository_in_sync(self, repository, last_validated_commit_data):
        current_branch = last_validated_commit_data.get(
            "branch", repository.default_branch
        )
        last_validated_commit = Commitish.from_hash(
            last_validated_commit_data["commit"]
        )

        try:
            top_commit_of_branch = repository.top_commit_of_remote_branch(
                current_branch
            )
        except GitError:
            if repository.is_bare_repository:
                # Check if the user's local repository has the branch
                if current_branch in repository.branches:
                    repository.create_branch(current_branch)
                    # Create the branch in the temp repository
                    top_commit_of_branch = repository.top_commit_of_branch(
                        current_branch
                    )
                else:
                    return False
            else:
                if not repository.branch_exists(current_branch, include_remotes=False):
                    return False
                top_commit_of_branch = repository.top_commit_of_branch(current_branch)

        if top_commit_of_branch != last_validated_commit:
            # check if top commit is newer (which is fine, it will be validated)
            # or older, meaning that the authentication repository contains
            # additional commits, so it would be necessary to find older auth repo
            # commit and start the validation from there
            if current_branch not in repository.branches_containing_commit(
                last_validated_commit
            ):
                return False
            self.state.old_heads_per_target_repos_branches[repository.name][
                current_branch
            ] = last_validated_commit

        return True

    def reset_target_repositories(self):
        for repository in self.state.users_target_repositories.values():
            # Reset information about the top commits of user's repositories
            for branch in self.state.old_heads_per_target_repos_branches[
                repository.name
            ]:
                self.state.old_heads_per_target_repos_branches[repository.name][
                    branch
                ] = None

    def _update_state_for_initial_sync(self):
        self.state.last_validated_commit = None
        self.state.last_validated_data = {}
        self.state.auth_commits_since_last_validated = (
            self.state.users_auth_repo.all_commits_on_branch(
                self.state.users_auth_repo.default_branch
            )
        )
        self.state.all_targets_auth_commits = (
            self.state.auth_commits_since_last_validated
        )
        # append fetched commits
        if self.state.update_handler is not None and self.state.update_handler.commits:
            self.state.auth_commits_since_last_validated.extend(
                self.state.update_handler.commits[1:]
            )
        self.state.targets_data_by_auth_commits = (
            self.state.users_auth_repo.targets_data_by_auth_commits(
                self.state.all_targets_auth_commits,
                target_repos=self.state.users_target_repositories,
            )
        )

    def get_targets_data_from_auth_repo(self):
        repo_branches = {}
        for repo_name, commits_data in self.state.targets_data_by_auth_commits.items():
            branches = set()  # using a set to avoid duplicate branches
            for commit_data in commits_data.values():
                branches.add(commit_data["branch"])
            repo_branches[repo_name] = sorted(list(branches))
        self.state.target_branches_data_from_auth_repo = repo_branches
        return UpdateStatus.SUCCESS

    def get_target_repositories_commits(self):
        """Returns a list of newly fetched commits belonging to the specified branch."""
        taf_logger.debug(
            f"{self.state.auth_repo_name}: Fetching commits of target repositories..."
        )
        self.state.fetched_commits_per_target_repos_branches = defaultdict(dict)

        def fetch_commits(repository, branch, old_head):
            fetched_commits_on_target_repo_branch = []
            local_branch_exists = repository.branch_exists(
                branch, include_remotes=False
            )
            branch_exists = repository.branch_exists(branch, include_remotes=True)

            if repository.name in self.state.repos_on_disk:
                if self.only_validate:
                    if not branch_exists:
                        self.state.targets_data = {}
                        msg = f"{repository.name} does not contain a branch named {branch} and cannot be validated. Please update the repositories."
                        taf_logger.error(msg)
                        raise UpdateFailedError(msg)
                else:
                    repository.fetch(branch=branch)

            if old_head is not None:
                if not self.only_validate:
                    fetched_commits = repository.all_commits_on_branch(
                        branch=f"origin/{branch}"
                    )
                    if old_head in fetched_commits:
                        fetched_commits_on_target_repo_branch = fetched_commits[
                            fetched_commits.index(old_head) + 1 :
                        ]
                    else:
                        fetched_commits_on_target_repo_branch = (
                            repository.all_commits_since_commit(old_head, branch)
                        )
                        for commit in fetched_commits:
                            if commit not in fetched_commits_on_target_repo_branch:
                                fetched_commits_on_target_repo_branch.append(commit)
                else:
                    fetched_commits_on_target_repo_branch = (
                        repository.all_commits_since_commit(old_head, branch)
                    )
                fetched_commits_on_target_repo_branch.insert(0, old_head)
            else:
                if local_branch_exists:
                    fetched_commits_on_target_repo_branch = (
                        repository.all_commits_on_branch(branch=branch, reverse=True)
                    )
                else:
                    fetched_commits_on_target_repo_branch = []
                try:
                    fetched_commits = repository.all_commits_on_branch(
                        branch=f"origin/{branch}"
                    )
                    for commit in fetched_commits:
                        if commit not in fetched_commits_on_target_repo_branch:
                            fetched_commits_on_target_repo_branch.append(commit)
                except GitError:
                    pass

            return branch, fetched_commits_on_target_repo_branch

        with ThreadPoolExecutor() as executor:
            future_to_branch = {
                executor.submit(
                    fetch_commits,
                    repository,
                    branch,
                    self.state.old_heads_per_target_repos_branches[repository.name].get(
                        branch
                    ),
                ): repository.name
                for repository in self.state.temp_target_repositories.values()
                if repository.name in self.state.target_branches_data_from_auth_repo
                for branch in self.state.target_branches_data_from_auth_repo[
                    repository.name
                ]
            }

            for future in as_completed(future_to_branch):
                try:
                    branch, commits = future.result()
                    repository_name = future_to_branch[future]
                    self.state.fetched_commits_per_target_repos_branches[
                        repository_name
                    ][branch] = commits
                except Exception as e:
                    self.state.errors.append(e)
                    self.state.event = Event.FAILED
                    return UpdateStatus.FAILED
        return UpdateStatus.SUCCESS

    def check_if_local_target_repositories_clean(self):
        taf_logger.debug(
            f"{self.state.auth_repo_name}: Checking if newly added target repositories are clean..."
        )
        try:
            (
                dirty_index_repos,
                unpushed_commits_repos_and_branches,
            ) = self._check_if_target_repos_clean(
                self.state.repos_on_disk.values(),
                self.state.target_branches_data_from_auth_repo,
            )

            if (
                len(dirty_index_repos) > 0
                or len(unpushed_commits_repos_and_branches) > 0
            ):
                raise MultipleRepositoriesNotCleanError(
                    dirty_index_repos, unpushed_commits_repos_and_branches
                )
            return UpdateStatus.SUCCESS
        except Exception as e:
            self.state.errors.append(e)
            self.state.event = Event.FAILED
            return UpdateStatus.FAILED

    def validate_target_repositories(self):
        """
        Breadth-first update of target repositories
        Merge last valid commits at the end of the update
        """
        taf_logger.info(
            f"{self.state.auth_repo_name}: Validating target repositories..."
        )
        try:
            # need to be set to old head since that is the last validated target
            self.state.validated_commits_per_target_repos_branches = defaultdict(dict)

            self.state.last_validated_data_per_repositories = defaultdict(dict)
            self.state.validated_auth_commits = []
            for auth_commit in self.state.all_targets_auth_commits:
                for repository in self.state.temp_target_repositories.values():
                    if repository.name not in self.state.targets_data_by_auth_commits:
                        continue
                    if (
                        auth_commit
                        not in self.state.targets_data_by_auth_commits[repository.name]
                    ):
                        continue
                    current_targets_data = self.state.targets_data_by_auth_commits[
                        repository.name
                    ][auth_commit]

                    current_branch = current_targets_data.get(
                        "branch", repository.default_branch
                    )
                    current_commit = Commitish.from_hash(current_targets_data["commit"])
                    if not len(
                        self.state.last_validated_data_per_repositories[repository.name]
                    ):
                        last_validated_target_auth_commit = (
                            self._get_last_validated_commit(repository.name)
                        )
                        current_head_commit_and_branch = (
                            self.state.targets_data_by_auth_commits[
                                repository.name
                            ].get(last_validated_target_auth_commit, {})
                        )
                        previous_branch = current_head_commit_and_branch.get("branch")
                        previous_commit = Commitish.from_hash(
                            current_head_commit_and_branch.get("commit")
                        )
                        if previous_commit is not None and previous_branch is None:
                            previous_branch = repository.default_branch
                    else:
                        previous_branch = (
                            self.state.last_validated_data_per_repositories[
                                repository.name
                            ].get("branch")
                        )
                        previous_commit = (
                            self.state.last_validated_data_per_repositories[
                                repository.name
                            ]["commit"]
                        )

                    target_commits_from_target_repo = (
                        self.state.fetched_commits_per_target_repos_branches[
                            repository.name
                        ]
                    )
                    validated_commit = self._validate_current_repo_commit(
                        repository,
                        self.state.users_auth_repo,
                        previous_branch,
                        previous_commit,
                        current_branch,
                        current_commit,
                        target_commits_from_target_repo,
                        auth_commit,
                    )

                    self.state.last_validated_data_per_repositories[repository.name] = {
                        "commit": validated_commit,
                        "branch": current_branch,
                    }

                    self.state.validated_commits_per_target_repos_branches[
                        repository.name
                    ].setdefault(current_branch, []).append(validated_commit)

                # commit processed without an error
                self.state.validated_auth_commits.append(auth_commit)
            taf_logger.info(
                f"{self.state.auth_repo_name}: Validation of target repositories finished"
            )
            return UpdateStatus.SUCCESS
        except Exception as e:
            self.state.errors.append(e)
            taf_logger.error(e)
            if len(self.state.validated_auth_commits):
                self.state.event = Event.PARTIAL
                return UpdateStatus.PARTIAL
            self.state.event = Event.FAILED
            return UpdateStatus.FAILED

    def _validate_current_repo_commit(
        self,
        repository,
        users_auth_repo,
        previous_branch,
        previous_commit,
        current_branch,
        current_commit,
        target_commits_from_target_repo,
        current_auth_commit,
    ):
        target_commits_from_target_repos_on_branch = target_commits_from_target_repo[
            current_branch
        ]
        if previous_commit == current_commit:
            # target not updated in this revision
            return current_commit
        if previous_branch == current_branch:
            # same branch
            current_target_commit = _find_next_value(
                previous_commit, target_commits_from_target_repos_on_branch
            )
        else:
            # next branch
            current_target_commit = target_commits_from_target_repos_on_branch[0]

        if current_target_commit is None:
            # there are commits missing from the target repository
            commit_date = users_auth_repo.get_commit_date(current_auth_commit)
            raise UpdateFailedError(
                f"Failure to validate {users_auth_repo.name} commit {current_auth_commit} committed on {commit_date}: \
data repository {repository.name} was supposed to be at commit {current_commit} \
but commit not on branch {current_branch}"
            )

        if current_commit == current_target_commit:
            return current_target_commit
        if not _is_unauthenticated_allowed(repository):
            commit_date = users_auth_repo.get_commit_date(current_auth_commit)
            raise UpdateFailedError(
                f"Failure to validate {users_auth_repo.name} commit {current_auth_commit} committed on {commit_date}: \
data repository {repository.name} was supposed to be at commit {current_commit} \
but repo was at {current_target_commit}"
            )
        # unauthenticated commits are allowed, try to skip them
        # if commits of the target repositories were swapped, commit which is expected to be found
        # after the current one will be skipped and it won't be found later, so validation will fail
        remaining_commits = target_commits_from_target_repos_on_branch[
            target_commits_from_target_repos_on_branch.index(current_target_commit) :
        ]
        for target_commit in remaining_commits:
            if current_commit == target_commit:
                return target_commit
            taf_logger.debug(
                f"{repository.name}: skipping target commit {target_commit}. Looking for commit {current_commit}"
            )
        commit_date = users_auth_repo.get_commit_date(current_auth_commit)
        raise UpdateFailedError(
            f"Failure to validate {users_auth_repo.name} commit {current_auth_commit} committed on {commit_date}: \
data repository {repository.name} was supposed to be at commit {current_commit} \
but commit not on branch {current_branch}"
        )

    def validate_and_set_additional_commits_of_target_repositories(self):
        """
        For target repository and for each branch, extract commits following the last validated commit
        These commits are not invalid. In case of repositories which cannot contain unauthenticated commits
        all of these commits will have to get signed if at least one commits on that branch needs to get signed
        However, no error will get reported if there are commits which have not yet been signed
        In case of repositories which can contain unauthenticated commits, they do not even need to get signed
        """
        taf_logger.debug(
            f"{self.state.auth_repo_name}: Validating and setting additional commits of target repositories..."
        )
        # only get additional commits if the validation was complete (not partial, up to a commit)
        self.state.additional_commits_per_target_repos_branches = defaultdict(dict)
        if self.state.update_status != UpdateStatus.SUCCESS:
            return self.state.update_status
        try:
            for repository in self.state.temp_target_repositories.values():
                # this will only include branches that were, at least partially, validated (up until a certain point)
                for (
                    branch,
                    validated_commits,
                ) in self.state.validated_commits_per_target_repos_branches[
                    repository.name
                ].items():
                    last_validated_commit = validated_commits[-1]
                    branch_commits = (
                        self.state.fetched_commits_per_target_repos_branches[
                            repository.name
                        ][branch]
                    )
                    additional_commits = branch_commits[
                        branch_commits.index(last_validated_commit) + 1 :
                    ]
                    if len(additional_commits):
                        if (
                            not _is_unauthenticated_allowed(repository)
                            and not self.no_upstream
                        ):
                            raise UpdateFailedError(
                                f"Target repository {repository.name} does not allow unauthenticated commits, but contains commit(s) {', '.join([commit.value for commit in additional_commits])} on branch {branch}"
                            )

                        # these commits include all commits newer than last authenticated commit (if unauthenticated commits are allowed)
                        # that does not necessarily mean that the local repository is not up to date with the remote
                        # pull could've been run manually
                        # check where the current local head is
                        branch_current_head = repository.top_commit_of_branch(branch)
                        if branch_current_head in additional_commits:
                            additional_commits = additional_commits[
                                additional_commits.index(branch_current_head) + 1 :
                            ]
                    self.state.additional_commits_per_target_repos_branches[
                        repository.name
                    ][branch] = additional_commits
            return self.state.update_status
        except UpdateFailedError as e:
            self.state.errors.append(e)
            taf_logger.error(e)
            self.state.event = Event.PARTIAL
            return UpdateStatus.PARTIAL
        except Exception as e:
            self.state.errors.append(e)
            taf_logger.error(e)
            self.state.event = Event.FAILED
            return UpdateStatus.FAILED

    def update_users_target_repositories(self):
        taf_logger.debug(
            f"{self.state.auth_repo_name}: Copying or updating user's target repositories..."
        )
        if self.state.update_status == UpdateStatus.FAILED:
            return self.state.update_status
        try:
            for repository_name in self.state.repos_not_on_disk:
                branches = [
                    branch
                    for branch in self.state.validated_commits_per_target_repos_branches[
                        repository_name
                    ]
                ]
                users_target_repo = self.state.users_target_repositories[
                    repository_name
                ]
                temp_target_repo = self.state.temp_target_repositories[repository_name]
                users_target_repo.clone_from_disk(
                    temp_target_repo.path,
                    temp_target_repo.get_remote_url(),
                    is_bare=self.bare,
                    branches=branches,
                )
            for repository_name in self.state.repos_on_disk:
                users_target_repo = self.state.users_target_repositories[
                    repository_name
                ]
                temp_target_repo = self.state.temp_target_repositories[repository_name]
                branches = self.state.validated_commits_per_target_repos_branches[
                    repository_name
                ]
                for branch in branches:
                    temp_target_repo.update_local_branch(branch=branch)
                users_target_repo.fetch_from_disk(temp_target_repo.path, branches)

            return self.state.update_status
        except Exception as e:
            self.state.errors.append(e)
            taf_logger.error(e)
            self.state.event = Event.FAILED
            return UpdateStatus.FAILED

    def remove_temp_repositories(self):
        taf_logger.debug(f"{self.state.auth_repo_name}: Removing temp repositories...")
        if not self.state.temp_root:
            return self.state.update_status
        try:
            for repo in self.state.temp_target_repositories.values():
                repo.cleanup()
            self.state.temp_root.cleanup()
            self.state.update_handler.cleanup()
        except Exception:
            taf_logger.warning(
                f"WARNING: Could not remove clean up temp folder: {self.state.temp_root}. Please remove it manually."
            )
        return self.state.update_status

    def merge_commits(self):
        """Determines which commits needs to be merged into the specified branch and
        merge it.
        """
        taf_logger.info(
            f"{self.state.auth_repo_name}: Merging commits into target repositories..."
        )
        events_list = []
        try:
            if self.only_validate:
                return self.state.update_status
            if self.state.update_status == UpdateStatus.FAILED:
                return self.state.update_status
            for repository in self.state.users_target_repositories.values():
                # this will only include branches that were, at least partially, validated (up until a certain point)
                last_branch = self.state.last_validated_data_per_repositories[
                    repository.name
                ]["branch"]
                for (
                    branch,
                    validated_commits,
                ) in self.state.validated_commits_per_target_repos_branches[
                    repository.name
                ].items():
                    is_last_branch = branch == last_branch
                    last_validated_commit = validated_commits[-1]
                    commit_to_merge = last_validated_commit
                    update_status = self._merge_commit(
                        repository, branch, commit_to_merge, is_last_branch
                    )
                    events_list.append(update_status)

            if self.state.event == Event.UNCHANGED and Event.CHANGED in events_list:
                # the auth repository was not updated, but one of the target repositories was
                self.state.event = Event.CHANGED

            return self.state.update_status
        except Exception as e:
            self.state.errors.append(e)
            self.state.event = Event.FAILED
            return UpdateStatus.FAILED

    def merge_auth_commits(self):
        """Determines which commits needs to be merged into the specified branch and
        merge it.
        """
        taf_logger.info(
            f"{self.state.auth_repo_name}: Merging commit into auth repo..."
        )
        try:
            if self.only_validate:
                return self.state.update_status
            if self.state.update_status == UpdateStatus.FAILED:
                return self.state.update_status
            if self.no_upstream and self.state.event == Event.UNCHANGED:
                # if no upstream and unchanged, there are no validated auth commits
                # (which are set when valiating targets)
                # but the top commit of the auth repo should've been validated
                # call merge again as that can clean up a messy state of that repository
                # such as it being in the detached head state
                last_commit = self.state.auth_commits_since_last_validated[0]
            else:
                last_commit = self.state.validated_auth_commits[-1]

            self._merge_commit(
                self.state.users_auth_repo,
                self.state.users_auth_repo.default_branch,
                last_commit,
                True,
            )

            # store information about which target (data) repositories were updated
            # some might have been omitted if the update was run with --exclude-target
            last_validated_data = self.state.last_validated_data or {}
            for repo in self.state.users_target_repositories.keys():
                last_validated_data[repo] = last_commit.value
            last_validated_data[self.state.users_auth_repo.name] = last_commit.value
            self.state.users_auth_repo.set_last_validated_data(
                last_validated_data,
                set_last_validated_commit=not bool(self.excluded_target_globs),
            )

            return self.state.update_status
        except Exception as e:
            self.state.errors.append(e)
            self.state.event = Event.FAILED
            return UpdateStatus.FAILED

    def _merge_commit(
        self,
        repository: AuthenticationRepository,
        branch: str,
        commit_to_merge: Commitish,
        is_last_branch: bool,
    ):
        """Merge the specified commit into the given branch and check out the branch.
        If the repository cannot contain unauthenticated commits, check out the merged commit.
        """
        if repository.is_bare_repository:
            repository.update_ref_for_bare_repository(branch, commit_to_merge)
            return

        # if the repo is in a deteched head state or if the updated branch exists,
        # but is not checked out, update the repo without automatically checking
        # out the newest branch and print a warning
        # if run with --force, checkout the newest branch regardless of the repo's state

        checkout_branch = is_last_branch
        local_branch_exists = repository.branch_exists(branch, include_remotes=False)
        if is_last_branch and not self.force:
            try:
                if repository.is_detached_head:
                    self.state.warnings.append(
                        f"Repository {repository.name} in a detached HEAD state. Checkout the newest branch manually or run the updater with --force"
                    )
                    checkout_branch = False
                else:
                    current_branch = repository.get_current_branch()
                    if local_branch_exists and current_branch != branch:
                        self.state.warnings.append(
                            f"Repository {repository.name} on branch {current_branch}. Checkout the newest branch manually or run the updater with --force"
                        )
                        checkout_branch = False
            except KeyError:
                # an error will be raised if the repo is empty
                pass

        if checkout_branch:
            try:
                repository.checkout_branch(branch, raise_anyway=True)
            except GitError as e:
                # two scenarios:
                # current git repository is in an inconsistent state:
                # - .git/index.lock exists (git partial update got applied)
                # should get addressed in https://github.com/openlawlibrary/taf/issues/210
                taf_logger.error(
                    "Could not checkout branch {} during commit merge. Error {}",
                    branch,
                    e,
                )
                raise UpdateFailedError(
                    f"Repository {repository.name} should contain only committed changes. \n"
                    f"Please update the repository at {repository.path} manually and try again."
                )
        elif not local_branch_exists:
            repository.create_local_branch_from_remote_tracking(branch)

        if repository.top_commit_of_branch(branch) == commit_to_merge:
            return Event.UNCHANGED

        taf_logger.info(
            "{} Merging commit {} into branch {}",
            repository.name,
            format_commit(commit_to_merge),
            branch,
        )
        repository.merge_commit(commit_to_merge, target_branch=branch)

        return Event.CHANGED

    def set_target_repositories_data(self):
        try:
            targets_data = {}
            for repo_name, repo in self.state.users_target_repositories.items():
                targets_data[repo_name] = {"repo_data": repo.to_json_dict()}
                if repo_name not in self.state.targets_data_by_auth_commits:
                    continue
                commits_data = self.state.targets_data_by_auth_commits[repo_name]

                branch_data = defaultdict(dict)

                # Iterate through auth_commits in the specified order
                for auth_commit in self.state.validated_auth_commits:
                    commit_info = commits_data.get(auth_commit)
                    if not commit_info or "branch" not in commit_info:
                        continue

                    branch = commit_info.pop("branch")

                    # Update the before_pull, after_pull, and new values
                    if branch not in branch_data:
                        old_head = self.state.old_heads_per_target_repos_branches.get(
                            repo_name, {}
                        ).get(branch)
                        branch_data[branch]["new"] = [commit_info]
                        branch_data[branch]["after_pull"] = [commit_info]
                        branch_data[branch][
                            "unauthenticated"
                        ] = self.state.additional_commits_per_target_repos_branches.get(
                            repo_name, {}
                        ).get(
                            branch, []
                        )
                        if old_head is not None:
                            branch_data[branch]["before_pull"] = old_head
                    else:
                        branch_data[branch]["new"].append(commit_info)
                        branch_data[branch]["after_pull"] = commit_info

                targets_data[repo_name]["commits"] = branch_data
            self.state.targets_data = targets_data
            return self.state.update_status
        except Exception as e:
            self.state.errors.append(e)
            self.state.event = Event.FAILED
            return UpdateStatus.FAILED

    def set_output(self):
        if self.state.auth_commits_since_last_validated is None:
            commit_before_pull = None
            new_commits = []
            commit_after_pull = None
        else:
            if self.state.event in (Event.UNCHANGED, Event.FAILED):
                if not self.state.existing_repo:
                    commit_before_pull = None
                else:
                    if len(self.state.auth_commits_since_last_validated):
                        commit_before_pull = (
                            self.state.auth_commits_since_last_validated[0]
                        )
                    else:
                        # self.state.auth_commits_since_last_validated might be an empty list if the update failed
                        commit_before_pull = (
                            self.state.users_auth_repo.top_commit_of_branch(
                                self.state.users_auth_repo.default_branch
                            )
                        )
                new_commits = []
                commit_after_pull = commit_before_pull
            else:
                commit_before_pull = (
                    self.state.validated_auth_commits[0]
                    if self.state.existing_repo
                    and len(self.state.validated_auth_commits)
                    else None
                )
                if len(self.state.validated_auth_commits):
                    commit_after_pull = self.state.validated_auth_commits[-1]
                else:
                    commit_after_pull = None

                if not self.state.existing_repo:
                    new_commits = self.state.validated_auth_commits
                else:
                    new_commits = (
                        self.state.validated_auth_commits[1:]
                        if len(self.state.validated_auth_commits)
                        else []
                    )

        commits_data = AuthCommitsData(
            before_pull=commit_before_pull,
            new=new_commits,
            after_pull=commit_after_pull,
        )

        if len(self.state.errors):
            message = "\n".join(str(error) for error in self.state.errors)
            error = UpdateFailedError(message)
        else:
            error = None

        warnings = ""
        if len(self.state.warnings):
            warnings = "\n".join(self.state.warnings)

        self._output = UpdateOutput(
            event=self.state.event,
            users_auth_repo=self.state.users_auth_repo,
            auth_repo_name=self.state.auth_repo_name,
            commits_data=commits_data,
            error=error,
            targets_data=self.state.targets_data,
            warnings=warnings,
        )

    def print_additional_commits(self):
        for (
            repo_name,
            branches,
        ) in self.state.additional_commits_per_target_repos_branches.items():
            for branch_name, additional_commits in branches.items():
                if len(additional_commits):
                    formatted_commits = _format_commits(additional_commits)
                    taf_logger.info(
                        f"Repository {repo_name}: found commits succeeding the last authenticated commit on branch {branch_name}: {formatted_commits}.\nThese commits were not merged into {branch_name}"
                    )
                    taf_logger.debug(
                        f"Repository {repo_name}: all commits: {','.join([commit.value for commit in additional_commits])}"
                    )

    def check_pre_push_hook(self):
        try:
            ensure_pre_push_hook(self.state.users_auth_repo.path)
            return UpdateStatus.SUCCESS
        except Exception as e:
            self.state.errors.append(e)
            self.state.event = Event.FAILED
            return UpdateStatus.FAILED


def _get_repository_name_raise_error_if_not_defined(validation_repo, commit):
    try:
        return _get_repository_name_from_info_json(validation_repo, commit)
    except MissingInfoJsonError as e:
        raise UpdateFailedError(str(e))


def _get_repository_name_from_info_json(auth_repo, commit_sha):
    try:
        info = auth_repo.get_json(commit_sha, INFO_JSON_PATH)
        return f'{info["namespace"]}/{info["name"]}'
    except Exception:
        raise MissingInfoJsonError(
            "Error during info.json parse. If the authentication repository's path is not specified, info.json metadata is expected to be in targets/protected"
        )


def _is_unauthenticated_allowed(repository):
    return repository.custom.get("allow-unauthenticated-commits", False)


def _remove_unpushed_commits(repository, branch, unpushed_commits):
    repository.clean_and_reset()
    repository.checkout_branch(branch)
    repository.reset_num_of_commits(len(unpushed_commits), hard=True)


def _run_tuf_updater(git_fetcher, auth_repo_name):
    auth_repo_name = auth_repo_name or ""
    taf_logger.info(f"{auth_repo_name}: Running TUF validation...")

    def _init_updater():
        try:
            return Updater(
                git_fetcher.metadata_dir,
                "metadata/",
                git_fetcher.targets_dir,
                "targets/",
                fetcher=git_fetcher,
            )
        except Exception as e:
            taf_logger.error(
                f"{auth_repo_name}: Failed to instantiate TUF Updater due to error: {e}"
            )
            raise e

    last_validated_commit = None
    try:
        while not git_fetcher.update_done():
            updater = _init_updater()
            current_commit = _update_tuf_current_revision(
                git_fetcher, updater, auth_repo_name
            )
            if current_commit is not None:
                last_validated_commit = current_commit
    except UpdateFailedError as e:
        return last_validated_commit, e

    return last_validated_commit, None


def _update_tuf_current_revision(git_fetcher, updater, auth_repo_name):
    current_commit = git_fetcher.current_commit
    try:
        auth_repo_name = auth_repo_name or ""
        updater.refresh()
        taf_logger.debug(
            f"{auth_repo_name}: Validated metadata files at revision {current_commit}"
        )
        # using refresh, we have updated all main roles
        # we still need to update the delegated roles (if there are any)
        # and validate any target files

        current_targets = git_fetcher.get_current_targets()
        for target_path in current_targets:
            target_filepath = target_path.replace("\\", "/")
            targetinfo = updater.get_targetinfo(target_filepath)
            target_data = git_fetcher.get_current_target_data(target_filepath, raw=True)
            targetinfo.verify_length_and_hashes(target_data)

            taf_logger.debug(
                f"{auth_repo_name}: Successfully validated target file {target_filepath} at {current_commit}"
            )
        if settings.strict:
            _validate_metadata_on_disk(git_fetcher)
        return current_commit
    except Exception as e:
        metadata_expired = EXPIRED_METADATA_ERROR in type(
            e
        ).__name__ or EXPIRED_METADATA_ERROR in str(e)
        if not metadata_expired or settings.strict:
            taf_logger.error(
                f"{auth_repo_name}: Validation of authentication repository failed at revision {current_commit} due to error: {e}"
            )
            raise UpdateFailedError(
                f"Validation of authentication repository {auth_repo_name or ''}"
                f" failed at revision {current_commit} due to error: {e}"
            )
        taf_logger.debug(
            f"WARNING: Could not validate {auth_repo_name} at revision {current_commit} due to error: {e}"
        )


def _check_if_commit_on_branch(repo, commit, branch, include_remotes=True):
    if not repo.commit_exists(commit=commit):
        return False

    try:
        branches_containing_last_validated_commit = repo.branches_containing_commit(
            commit
        )
    except GitError:
        return False

    if branch in branches_containing_last_validated_commit:
        return True
    if include_remotes:
        return f"origin/{branch}" in branches_containing_last_validated_commit
    return False


def _validate_metadata_on_disk(git_fetcher):
    """
    TUF updater does not always check the validity of all metadata files
    if timestamp is not updated, the updater will determine that a new version
    of the snapshot file does not need to be downloaded and it will not be validated
    during the update process, the metadata files that TUF updater downloads is stored
    in a separate folder within the temp directory
    For each commit, check if the metadata files inside that directory are the same
    as the ones in the auth repository's metadata folder at that revision
    """
    consistent_snaphost_pattern = r"\d+\.[^\.\s]+\.\w+"
    for metadata_file_name in git_fetcher.get_current_metadata():
        # version (consistent snapshot files) are downloaded to remote
        # by the TUF updater, but saved to the main metadata file
        # so, 2.root.json is downloaded and saved to root.json
        if re.search(consistent_snaphost_pattern, metadata_file_name):
            continue

        current_tuf_metadata_file = Path(git_fetcher.metadata_dir, metadata_file_name)
        if not current_tuf_metadata_file.is_file():
            # this validation causes an issue with one of the first
            # commits of our production repositories and it should
            # not be enabled until we specify a later commit of those
            # repositories as the initial valid ones
            # this error happens when a metadata file is added, but
            # snapshot is not updated
            # raise UpdateFailedError(
            #     f"Invalid metadata file {metadata_file_name}"
            # )
            continue
        metadata_content = git_fetcher.get_current_metadata_data(metadata_file_name)
        tuf_metadata_content = current_tuf_metadata_file.read_text()
        if metadata_content != tuf_metadata_content:
            raise UpdateFailedError(f"Invalid metadata file {metadata_file_name}")


def _find_next_value(value, values_list):
    """
    Find the next value in the list after the given value.

    Parameters:
    - value: The value to look for.
    - values_list: The list of values.

    Returns:
    - The next value in the list after the given value, or None if there isn't one.
    """
    try:
        index = values_list.index(value)
        if index < len(values_list) - 1:  # check if there are remaining values
            return values_list[index + 1]
    except ValueError:
        pass  # value not in list
    return None


def _format_commits(commits: List[Commitish]) -> str:
    """
    Utility function to format the commits in a readable way.
    """
    commits = [format_commit(commit) for commit in commits]
    if len(commits) > 2:
        formatted_commits = f"{commits[0]} ... {commits[-1]}"
    elif len(commits) == 2:
        formatted_commits = f"{commits[0]} and {commits[1]}"
    else:
        formatted_commits = commits[0].hash
    return formatted_commits
