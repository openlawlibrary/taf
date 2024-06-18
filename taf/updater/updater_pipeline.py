from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from enum import Enum
import functools
from logging import DEBUG, INFO
from pathlib import Path
import re
import shutil
import tempfile
from typing import Any, Dict, List, Optional
from attr import attrs, define, field
from taf.git import GitError
from logdecorator import log_on_end, log_on_start
from taf.git import GitRepository

import taf.settings as settings
import taf.repositoriesdb as repositoriesdb
from taf.auth_repo import AuthenticationRepository
from taf.exceptions import (
    MissingInfoJsonError,
    RepositoryNotCleanError,
    UpdateFailedError,
    UnpushedCommitsError,
)
from taf.updater.handlers import GitUpdater
from taf.updater.lifecycle_handlers import Event
from taf.updater.types.update import OperationType, UpdateType
from taf.utils import TempPartition, on_rm_error
from taf.log import taf_logger
from tuf.ngclient.updater import Updater
from tuf.repository_tool import TARGETS_DIRECTORY_NAME


EXPIRED_METADATA_ERROR = "ExpiredMetadataError"
PROTECTED_DIRECTORY_NAME = "protected"
INFO_JSON_PATH = f"{TARGETS_DIRECTORY_NAME}/{PROTECTED_DIRECTORY_NAME}/info.json"


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
    auth_commits_since_last_validated: List[Any] = field(factory=list)
    existing_repo: bool = field(default=False)
    is_test_repo: bool = field(default=False)
    update_status: UpdateStatus = field(default=None)
    update_successful: bool = field(default=False)
    event: Optional[str] = field(default=None)
    users_auth_repo: Optional["AuthenticationRepository"] = field(default=None)
    validation_auth_repo: Optional["AuthenticationRepository"] = field(default=None)
    auth_repo_name: Optional[str] = field(default=None)
    errors: Optional[List[Exception]] = field(default=None)
    targets_data: Dict[str, Any] = field(factory=dict)
    last_validated_commit: str = field(factory=str)
    # repositories inside the temp folder which are created and cleaned up
    # during the update process
    temp_target_repositories: Dict[str, "GitRepository"] = field(factory=dict)
    # permanent repositories inside the user's local direcotry
    users_target_repositories: Dict[str, "GitRepository"] = field(factory=dict)
    # a dictionary of repositories which are already present inside a user's local and
    # directory when the update is started
    repos_on_disk: Dict[str, GitRepository] = field(factory=dict)
    # a dictionary of repositories which are not present inside a user's local
    # directory when the update is started
    repos_not_on_disk: Dict[str, GitRepository] = field(factory=dict)
    target_branches_data_from_auth_repo: Dict = field(factory=dict)
    targets_data_by_auth_commits: Dict = field(factory=dict)
    old_heads_per_target_repos_branches: Dict[str, Dict[str, str]] = field(factory=dict)
    fetched_commits_per_target_repos_branches: Dict[str, Dict[str, List[str]]] = field(
        factory=dict
    )
    validated_commits_per_target_repos_branches: Dict[str, Dict[str, str]] = field(
        factory=dict
    )
    additional_commits_per_target_repos_branches: Dict[
        str, Dict[str, List[str]]
    ] = field(factory=dict)
    validated_auth_commits: List[str] = field(factory=list)
    temp_root: TempPartition = field(default=None)


@attrs
class UpdateOutput:
    event: str = field()
    users_auth_repo: Any = field()
    auth_repo_name: str = field()
    commits_data: Dict[str, Any] = field()
    error: Optional[Exception] = field(default=None)
    targets_data: Dict[str, Any] = field(factory=dict)


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


def format_commit(commit):
    return commit[:10]


class Pipeline:
    def __init__(self, steps, run_mode):
        self.steps = steps
        self.current_step = None
        self.run_mode = run_mode

    def run(self):
        self.state.errors = []
        for step, step_run_mode in self.steps:
            try:
                if step_run_mode == RunMode.ALL or step_run_mode == self.run_mode:
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

        super().__init__(
            steps=[
                (self.set_existing_repositories, RunMode.UPDATE),
                (self.check_if_local_repositories_clean, RunMode.UPDATE),
                (self.clone_remote_and_run_tuf_updater, RunMode.ALL),
                (self.validate_out_of_band_and_update_type, RunMode.ALL),
                (self.clone_or_fetch_users_auth_repo, RunMode.UPDATE),
                (self.load_target_repositories, RunMode.ALL),
                (self.check_if_repositories_on_disk, RunMode.LOCAL_VALIDATION),
                (self.clone_target_repositories_to_temp, RunMode.UPDATE),
                (self.determine_start_commits, RunMode.ALL),
                (self.get_targets_data_from_auth_repo, RunMode.ALL),
                (
                    self.check_if_local_target_repositories_clean,
                    RunMode.UPDATE,
                ),
                (self.get_target_repositories_commits, RunMode.ALL),
                (self.validate_target_repositories, RunMode.ALL),
                (
                    self.validate_and_set_additional_commits_of_target_repositories,
                    RunMode.ALL,
                ),
                (self.update_users_target_repositories, RunMode.UPDATE),
                (self.merge_commits, RunMode.UPDATE),
                (self.remove_temp_repositories, RunMode.UPDATE),
                (self.set_target_repositories_data, RunMode.UPDATE),
                (self.print_additional_commits, RunMode.ALL),
            ],
            run_mode=RunMode.LOCAL_VALIDATION if only_validate else RunMode.UPDATE,
        )

        self.operation = operation
        self.url = url
        self.library_dir = library_dir
        self.auth_path = auth_path
        self.update_from_filesystem = update_from_filesystem
        self.expected_repo_type = expected_repo_type
        self.target_repo_classes = target_repo_classes
        self.target_factory = target_factory
        self.only_validate = only_validate
        self.validate_from_commit = validate_from_commit
        self.conf_directory_root = conf_directory_root
        self.out_of_band_authentication = out_of_band_authentication
        self.checkout = checkout
        self.excluded_target_globs = excluded_target_globs
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

    @log_on_start(
        DEBUG, "Checking which repositories are already on disk...", logger=taf_logger
    )
    def set_existing_repositories(self):
        self.state.existing_repo = False
        self.state.repos_on_disk = {}
        if self.auth_path is not None:
            auth_repo = AuthenticationRepository(path=self.auth_path)
            if auth_repo.is_git_repository_root:
                self.state.existing_repo = True
                # load target repositories in order to check if they are clean or synced
                # after updating the authentication repotiory, we need to load them again
                # since repositories.json could've changed
                repositoriesdb.load_repositories(
                    auth_repo,
                    library_dir=self.library_dir,
                    only_load_targets=True,
                    excluded_target_globs=self.excluded_target_globs,
                )
                target_repositories = repositoriesdb.get_deduplicated_repositories(
                    auth_repo,
                )
                self.state.repos_on_disk = {
                    target_repo.name: target_repo
                    for target_repo in target_repositories.values()
                    if target_repo.is_git_repository_root
                }
                repositoriesdb.clear_repositories_db()
        return UpdateStatus.SUCCESS

    @log_on_start(
        INFO,
        "Checking if local repositories are clean...",
        logger=taf_logger,
    )
    def check_if_local_repositories_clean(self):
        try:
            # check if the auth repo is clean first
            if self.state.existing_repo:
                auth_repo = AuthenticationRepository(path=self.auth_path)
                if auth_repo.something_to_commit():
                    raise RepositoryNotCleanError(auth_repo.name)
                if auth_repo.is_branch_with_unpushed_commits(auth_repo.default_branch):
                    raise UnpushedCommitsError(
                        auth_repo.name,
                        auth_repo.default_branch,
                    )
                # check target repositories which are on disk
                for repository in self.state.repos_on_disk.values():
                    if repository.something_to_commit():
                        raise RepositoryNotCleanError(repository.name)

                    # read the branch from the most recent target files (before the update)
                    # and check if it contains unpushed commits
                    # after the update, check if there are unpushed commits on any of the
                    # other branches
                    target = auth_repo.get_target(repository.name)
                    if not target or "branch" not in target:
                        continue
                    branch = target["branch"]
                    if repository.is_branch_with_unpushed_commits(branch):
                        raise UnpushedCommitsError(repository.name, branch)
        except Exception as e:
            self.state.errors.append(e)
            self.state.event = Event.FAILED
            return UpdateStatus.FAILED
        return UpdateStatus.SUCCESS

    @log_on_start(
        INFO, "Cloning repository and running TUF updater...", logger=taf_logger
    )
    @cleanup_decorator
    def clone_remote_and_run_tuf_updater(self):
        settings.update_from_filesystem = self.update_from_filesystem
        settings.conf_directory_root = self.conf_directory_root

        if self.operation == OperationType.CLONE_OR_UPDATE:
            if (
                self.auth_path is not None
                and AuthenticationRepository(path=self.auth_path).is_git_repository_root
            ):
                self.operation = OperationType.UPDATE
            else:
                self.operation = OperationType.CLONE

        # set last validated commit before running the updater
        # this last validated commit is read from the settings
        if self.operation == OperationType.CLONE:
            settings.last_validated_commit = None
        elif not settings.overwrite_last_validated_commit:
            users_auth_repo = AuthenticationRepository(path=self.auth_path)
            last_validated_commit = users_auth_repo.last_validated_commit
            settings.last_validated_commit = last_validated_commit

        try:
            self.state.auth_commits_since_last_validated = None

            # Use ThreadPoolExecutor to run _clone_validation_repo in a separate thread
            with ThreadPoolExecutor() as executor:
                future_validation_repo = executor.submit(
                    _clone_validation_repo, self.url
                )
                validation_repo = future_validation_repo.result()

            # check if auth path is provided and if that is not the case
            # check if info.json exists. info.json will be read after validation
            # at revision determined by the last validated commit
            # but we do not want the user to have to wait for the validation to be over
            # before raising an error because info.json is missing
            top_commit_of_validation_repo = validation_repo.top_commit_of_branch(
                validation_repo.default_branch
            )
            auth_repo_name = None
            git_updater = None

            if self.auth_path:
                auth_repo_name = GitRepository(path=self.auth_path).name
                self.state.auth_repo_name = auth_repo_name
            else:
                auth_repo_name = _get_repository_name_raise_error_if_not_defined(
                    validation_repo, top_commit_of_validation_repo
                )

            git_updater = GitUpdater(self.url, self.library_dir, validation_repo.name)
            last_validated_remote_commit, error = _run_tuf_updater(
                git_updater, auth_repo_name
            )
            if last_validated_remote_commit is None and error is not None:
                raise error

            # having validated the repository, read info.json from the last
            # valid commit if it is not the same as the most recent commit
            if self.state.auth_repo_name is None:
                if top_commit_of_validation_repo != last_validated_remote_commit:
                    self.state.auth_repo_name = (
                        _get_repository_name_raise_error_if_not_defined(
                            validation_repo, last_validated_remote_commit
                        )
                    )
                else:
                    self.state.auth_repo_name = auth_repo_name

            self.state.users_auth_repo = AuthenticationRepository(
                self.library_dir,
                self.state.auth_repo_name,
                urls=[self.url],
            )

            self.state.existing_repo = self.state.users_auth_repo.is_git_repository_root
            self._validate_operation_type()
            self.state.validation_auth_repo = git_updater.validation_auth_repo
            self.state.is_test_repo = self.state.validation_auth_repo.is_test_repo

            if self.operation == OperationType.UPDATE:
                self._validate_last_validated_commit(settings.last_validated_commit)

            # used for testing purposes
            if settings.overwrite_last_validated_commit:
                self.state.last_validated_commit = settings.last_validated_commit
            else:
                self.state.last_validated_commit = (
                    self.state.users_auth_repo.last_validated_commit
                )

            if error is None:
                self.state.auth_commits_since_last_validated = list(git_updater.commits)
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
                validated_commits_since_last_validated = []
                for commit in git_updater.commits:
                    validated_commits_since_last_validated.append(commit)
                    if commit == last_validated_remote_commit:
                        break

                self.state.auth_commits_since_last_validated = (
                    validated_commits_since_last_validated
                )
                self.state.errors.append(error)
                self.state.event = Event.PARTIAL
                return UpdateStatus.PARTIAL

        except Exception as e:
            self.state.errors.append(e)
            self.state.users_auth_repo = None

            if self.state.auth_repo_name is not None:
                self.state.users_auth_repo = AuthenticationRepository(
                    self.library_dir,
                    self.state.auth_repo_name,
                    urls=[self.url],
                    conf_directory_root=self.conf_directory_root,
                )
            self.state.event = Event.FAILED
            return UpdateStatus.FAILED
        finally:
            # always clean up repository updater
            if git_updater is not None:
                git_updater.cleanup()

    def _validate_operation_type(self):
        if self.operation == OperationType.CLONE and self.state.existing_repo:
            raise UpdateFailedError(
                f"Destination path {self.state.users_auth_repo.path} already exists and is not an empty directory. Run 'taf repo update' to update it."
            )
        elif self.operation == OperationType.UPDATE and not self.state.existing_repo:
            raise UpdateFailedError(
                f"{self.state.users_auth_repo.path} is not a Git repository. Run 'taf repo clone' instead"
            )

    @log_on_start(
        INFO, "Validating out of band commit and update type", logger=taf_logger
    )
    def validate_out_of_band_and_update_type(self):
        # this is the repository cloned inside the temp directory
        # we validate it before updating the actual authentication repository
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

    def _validate_last_validated_commit(self, last_validated_commit):
        branch = self.state.users_auth_repo.default_branch
        users_head_sha = self.state.users_auth_repo.top_commit_of_branch(branch)
        if last_validated_commit != users_head_sha:
            # if a user committed something to the repo or manually pulled the changes
            # last_validated_commit will no longer match the top commit, but the repository
            # might still be completely valid
            # committing without pushing is not valid
            # user_head_sha should be newer than last validated commit
            commits_since = self.state.users_auth_repo.all_commits_since_commit(
                since_commit=last_validated_commit, branch=branch
            )
            if users_head_sha not in commits_since:
                msg = f"Top commit of repository {self.state.users_auth_repo.name} {users_head_sha} and is not equal to or newer than last successful commit"
                taf_logger.error(msg)
                raise UpdateFailedError(msg)

    @log_on_start(
        INFO,
        "Cloning or updating user's authentication repository...",
        logger=taf_logger,
    )
    def clone_or_fetch_users_auth_repo(self):
        # fetch the latest commit or clone the repository without checkout
        # do not merge before targets are validated as well
        try:
            if self.state.existing_repo:
                self.state.users_auth_repo.fetch(fetch_all=True)
            else:
                self.state.users_auth_repo.clone()
        except Exception as e:
            self.state.errors.append(e)
            self.state.event = Event.FAILED
            return UpdateStatus.FAILED
        return UpdateStatus.SUCCESS

    @log_on_start(DEBUG, "Loading target repositories", logger=taf_logger)
    def load_target_repositories(self):
        try:
            repositoriesdb.load_repositories(
                self.state.users_auth_repo,
                repo_classes=self.target_repo_classes,
                factory=self.target_factory,
                library_dir=self.library_dir,
                commits=self.state.auth_commits_since_last_validated,
                only_load_targets=True,
                excluded_target_globs=self.excluded_target_globs,
            )
            self.state.users_target_repositories = (
                repositoriesdb.get_deduplicated_repositories(
                    self.state.users_auth_repo,
                    self.state.auth_commits_since_last_validated[-1::],
                )
            )
            if self.only_validate:
                self.state.temp_target_repositories = (
                    self.state.users_target_repositories
                )
            else:
                self.state.temp_root = TempPartition(self.state.users_auth_repo.path)
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

    @log_on_start(
        INFO,
        "Checking if all target repositories are already on disk...",
        logger=taf_logger,
    )
    def check_if_repositories_on_disk(self):
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

    @log_on_start(DEBUG, "Cloning target repositories to temp...", logger=taf_logger)
    @log_on_end(INFO, "Finished cloning target repositories", logger=taf_logger)
    def clone_target_repositories_to_temp(self):
        try:
            self.state.repos_on_disk = {}
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
                    temp_repo.clone(bare=True)
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

            return UpdateStatus.SUCCESS
        except Exception as e:
            self.state.errors.append(e)
            self.state.event = Event.FAILED
            return UpdateStatus.FAILED

    @log_on_start(
        INFO, "Validating initial state of target repositories...", logger=taf_logger
    )
    @log_on_end(
        INFO,
        "Checking initial state of repositories",
        logger=taf_logger,
    )
    def determine_start_commits(self):
        try:
            self.state.targets_data_by_auth_commits = (
                self.state.users_auth_repo.targets_data_by_auth_commits(
                    self.state.auth_commits_since_last_validated
                )
            )
            self.state.old_heads_per_target_repos_branches = defaultdict(dict)
            is_initial_state_in_sync = True
            # if last validated commit was not manually modified (set to a newer commit)
            # target repositories data that is extracted to them (commit and branch)
            # should be present in the local repository
            # if the local repository was manually modified (say, something was committed)
            # we still expect the last validated target commit to exist
            # and the remaining commits will be validated afterwards
            # if the last validated target commit does not exist, start the validation from scratch
            if self.state.last_validated_commit is not None:
                for repository in self.state.temp_target_repositories.values():
                    if repository.name not in self.state.targets_data_by_auth_commits:
                        continue
                    self.state.old_heads_per_target_repos_branches[repository.name] = {}
                    last_validated_repository_commits_data = (
                        self.state.targets_data_by_auth_commits[repository.name].get(
                            self.state.last_validated_commit, {}
                        )
                    )

                    if last_validated_repository_commits_data:
                        if repository.name in self.state.repos_not_on_disk:
                            is_initial_state_in_sync = False
                            break
                        current_branch = last_validated_repository_commits_data.get(
                            "branch", repository.default_branch
                        )
                        last_validated_commit = last_validated_repository_commits_data[
                            "commit"
                        ]

                        branch_exists = repository.branch_exists(
                            current_branch, include_remotes=False
                        )
                        if not branch_exists:
                            is_initial_state_in_sync = False
                            break
                        top_commit_of_branch = repository.top_commit_of_branch(
                            current_branch
                        )
                        if top_commit_of_branch != last_validated_commit:
                            # check if top commit is newer (which is fine, it will be validated)
                            # or older, meaning that the authentication repository contains
                            # additional commits, so it would be necessary to find older auth repo
                            # commit and start the validation from there
                            if (
                                current_branch
                                not in repository.branches_containing_commit(
                                    last_validated_commit
                                )
                            ):
                                is_initial_state_in_sync = False
                                break

                        self.state.old_heads_per_target_repos_branches[repository.name][
                            current_branch
                        ] = last_validated_commit

            if not is_initial_state_in_sync:
                taf_logger.info(
                    f"Repository {self.state.users_auth_repo.name}: states of target repositories are not in sync with last validated commit. Starting the update from the beginning"
                )
                self.state.last_validated_commit = None
                self.state.auth_commits_since_last_validated = (
                    self.state.users_auth_repo.all_commits_on_branch(
                        self.state.users_auth_repo.default_branch
                    )
                )
                self.state.targets_data_by_auth_commits = (
                    self.state.users_auth_repo.targets_data_by_auth_commits(
                        self.state.auth_commits_since_last_validated
                    )
                )
                # start validation from the beginning, so also removed
                # information about the top commits of user's repositories
                for repository in self.state.temp_target_repositories.values():
                    for branch in self.state.old_heads_per_target_repos_branches[
                        repository.name
                    ]:
                        self.state.old_heads_per_target_repos_branches[repository.name][
                            branch
                        ] = None

            return UpdateStatus.SUCCESS
        except Exception as e:
            self.state.errors.append(e)
            self.state.event = Event.FAILED
            return UpdateStatus.FAILED

    def get_targets_data_from_auth_repo(self):
        repo_branches = {}
        for repo_name, commits_data in self.state.targets_data_by_auth_commits.items():
            branches = set()  # using a set to avoid duplicate branches
            for commit_data in commits_data.values():
                branches.add(commit_data["branch"])
            repo_branches[repo_name] = sorted(list(branches))
        self.state.target_branches_data_from_auth_repo = repo_branches
        return UpdateStatus.SUCCESS

    @log_on_start(DEBUG, "Fetching commits of target repositories", logger=taf_logger)
    def get_target_repositories_commits(self):
        """Returns a list of newly fetched commits belonging to the specified branch."""
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

    @log_on_start(
        DEBUG,
        "Checking if target repositories contain unpushed commits...",
        logger=taf_logger,
    )
    def check_if_local_target_repositories_clean(self):
        try:
            for repository in self.state.repos_on_disk.values():
                if repository.something_to_commit():
                    raise RepositoryNotCleanError(repository.name)
                for branch in self.state.target_branches_data_from_auth_repo[
                    repository.name
                ]:
                    if repository.is_branch_with_unpushed_commits(branch):
                        raise UnpushedCommitsError(repository.name, branch)
        except Exception as e:
            self.state.errors.append(e)
            self.state.event = Event.FAILED
            return UpdateStatus.FAILED
        return UpdateStatus.SUCCESS

    @log_on_start(INFO, "Validating target repositories...", logger=taf_logger)
    @log_on_end(INFO, "Validation of target repositories finished", logger=taf_logger)
    def validate_target_repositories(self):
        """
        Breadth-first update of target repositories
        Merge last valid commits at the end of the update
        """
        try:
            # need to be set to old head since that is the last validated target
            self.state.validated_commits_per_target_repos_branches = defaultdict(dict)

            last_validated_data_per_repositories = defaultdict(dict)
            self.state.validated_auth_commits = []
            for auth_commit in self.state.auth_commits_since_last_validated:
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
                    current_commit = current_targets_data["commit"]
                    if not len(last_validated_data_per_repositories[repository.name]):
                        current_head_commit_and_branch = (
                            self.state.targets_data_by_auth_commits[
                                repository.name
                            ].get(self.state.last_validated_commit, {})
                        )
                        previous_branch = current_head_commit_and_branch.get("branch")
                        previous_commit = current_head_commit_and_branch.get("commit")
                        if previous_commit is not None and previous_branch is None:
                            previous_branch = repository.default_branch
                    else:
                        previous_branch = last_validated_data_per_repositories[
                            repository.name
                        ].get("branch")
                        previous_commit = last_validated_data_per_repositories[
                            repository.name
                        ]["commit"]

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

                    last_validated_data_per_repositories[repository.name] = {
                        "commit": validated_commit,
                        "branch": current_branch,
                    }

                    self.state.validated_commits_per_target_repos_branches[
                        repository.name
                    ].setdefault(current_branch, []).append(validated_commit)

                # commit processed without an error
                self.state.validated_auth_commits.append(auth_commit)
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

    @log_on_start(
        DEBUG,
        "Validating and setting additional commits of target repositories",
        logger=taf_logger,
    )
    def validate_and_set_additional_commits_of_target_repositories(self):
        """
        For target repository and for each branch, extract commits following the last validated commit
        These commits are not invalid. In case of repositories which cannot contain unauthenticated commits
        all of these commits will have to get signed if at least one commits on that branch needs to get signed
        However, no error will get reported if there are commits which have not yet been signed
        In case of repositories which can contain unauthenticated commits, they do not even need to get signed
        """
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
                        if not _is_unauthenticated_allowed(repository):
                            raise UpdateFailedError(
                                f"Target repository {repository.name} does not allow unauthenticated commits, but contains commit(s) {', '.join(additional_commits)} on branch {branch}"
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

    @log_on_start(
        DEBUG, "Copying or updating user's target repositories...", logger=taf_logger
    )
    def update_users_target_repositories(self):
        if self.state.update_status == UpdateStatus.FAILED:
            return self.state.update_status
        try:
            for repository_name in self.state.repos_not_on_disk:
                users_target_repo = self.state.users_target_repositories[
                    repository_name
                ]
                temp_target_repo = self.state.temp_target_repositories[repository_name]
                users_target_repo.clone_from_disk(
                    temp_target_repo.path, temp_target_repo.get_remote_url()
                )

            for repo_name in self.state.repos_on_disk:
                users_target_repo = self.state.users_target_repositories[repo_name]
                temp_target_repo = self.state.temp_target_repositories[repo_name]
                branches = self.state.validated_commits_per_target_repos_branches[
                    repo_name
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

    @log_on_start(DEBUG, "Removing temp repositories...", logger=taf_logger)
    def remove_temp_repositories(self):
        if not self.state.temp_root:
            return self.state.update_status
        try:
            for repo in self.state.temp_target_repositories.values():
                repo.cleanup()
            self.state.temp_root.cleanup()
        except Exception:
            taf_logger.warning(
                f"WARNING: Could not remove clean up temp folder: {self.state.temp_root}. Please remove it manually."
            )
        return self.state.update_status

    @log_on_start(
        INFO, "Merging commits into target repositories...", logger=taf_logger
    )
    def merge_commits(self):
        """Determines which commits needs to be merged into the specified branch and
        merge it.
        """
        try:
            if self.only_validate:
                return self.state.update_status
            if self.state.update_status == UpdateStatus.FAILED:
                return self.state.update_status
            for repository in self.state.users_target_repositories.values():
                # this will only include branches that were, at least partially, validated (up until a certain point)
                for (
                    branch,
                    validated_commits,
                ) in self.state.validated_commits_per_target_repos_branches[
                    repository.name
                ].items():
                    last_validated_commit = validated_commits[-1]
                    commit_to_merge = last_validated_commit
                    _merge_commit(
                        repository, branch, commit_to_merge, force_revert=True
                    )
            return self.state.update_status
        except Exception as e:
            self.state.errors.append(e)
            self.state.event = Event.FAILED
            return UpdateStatus.FAILED

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
            commit_before_pull = (
                self.state.validated_auth_commits[0]
                if self.state.existing_repo and len(self.state.validated_auth_commits)
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
        commits_data = {
            "before_pull": commit_before_pull,
            "new": new_commits,
            "after_pull": commit_after_pull,
        }

        if len(self.state.errors):
            message = "\n".join(str(error) for error in self.state.errors)
            error = UpdateFailedError(message)
        else:
            error = None

        self._output = UpdateOutput(
            event=self.state.event,
            users_auth_repo=self.state.users_auth_repo,
            auth_repo_name=self.state.auth_repo_name,
            commits_data=commits_data,
            error=error,
            targets_data=self.state.targets_data,
        )

    def print_additional_commits(self):
        for (
            repo_name,
            branches,
        ) in self.state.additional_commits_per_target_repos_branches.items():
            for branch_name, additional_commits in branches.items():
                if len(additional_commits):
                    formatted_commits = [
                        format_commit(commit) for commit in additional_commits
                    ]
                    taf_logger.info(
                        f"Repository {repo_name}: found commits succeeding the last authenticated commit on branch {branch_name}: {', '.join(formatted_commits)}.\nThese commits were not merged into {branch_name}"
                    )


def _clone_validation_repo(url):
    """
    Clones the authentication repository based on the url specified using the
    mirrors parameter. The repository is cloned as a bare repository
    to a the temp directory and will be deleted one the update is done.

    If repository_name isn't provided (default value), extract it from info.json.
    """
    temp_dir = tempfile.mkdtemp()
    path = Path(temp_dir, "auth_repo").absolute()
    validation_auth_repo = AuthenticationRepository(
        path=path, urls=[url], alias="Validation repository"
    )
    validation_auth_repo.clone(bare=True)
    validation_auth_repo.fetch(fetch_all=True)

    settings.validation_repo_path = validation_auth_repo.path

    validation_auth_repo.cleanup()
    return validation_auth_repo


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


@log_on_start(
    INFO,
    "Running TUF validation of the authentication repository...",
    logger=taf_logger,
)
def _run_tuf_updater(git_fetcher, auth_repo_name):
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
            taf_logger.error(f"Failed to instantiate TUF Updater due to error: {e}")
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
        updater.refresh()
        taf_logger.debug("Validated metadata files at revision {}", current_commit)
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
                "Successfully validated target file {} at {}",
                target_filepath,
                current_commit,
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
                "Validation of authentication repository {} failed at revision {} due to error: {}",
                auth_repo_name or "",
                current_commit,
                e,
            )
            raise UpdateFailedError(
                f"Validation of authentication repository {auth_repo_name or ''}"
                f" failed at revision {current_commit} due to error: {e}"
            )
        taf_logger.warning(
            f"WARNING: Could not validate authentication repository at revision {current_commit} due to error: {e}"
        )


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


def _merge_commit(repository, branch, commit_to_merge, force_revert=True):
    """Merge the specified commit into the given branch and check out the branch.
    If the repository cannot contain unauthenticated commits, check out the merged commit.
    """

    try:
        repository.checkout_branch(branch, raise_anyway=True)
    except GitError as e:
        # two scenarios:
        # current git repository is in an inconsistent state:
        # - .git/index.lock exists (git partial update got applied)
        # should get addressed in https://github.com/openlawlibrary/taf/issues/210
        # current git repository has uncommitted changes:
        # we do not want taf to lose any repo data, so we do not reset the repository.
        # for now, raise an update error and let the user manually reset the repository
        taf_logger.error(
            "Could not checkout branch {} during commit merge. Error {}", branch, e
        )
        raise UpdateFailedError(
            f"Repository {repository.name} should contain only committed changes. \n"
            f"Please update the repository at {repository.path} manually and try again."
        )

    if repository.top_commit_of_branch(branch) == commit_to_merge:
        return
    commits_since_to_merge = repository.all_commits_since_commit(
        commit_to_merge, branch=branch
    )
    if not len(commits_since_to_merge):
        taf_logger.info(
            "{} Merging commit {} into branch {}",
            repository.name,
            format_commit(commit_to_merge),
            branch,
        )
        repository.merge_commit(commit_to_merge)

    elif len(commits_since_to_merge) and force_revert:
        taf_logger.info(
            "{} Reverting branch {} to {}",
            repository.name,
            branch,
            format_commit(commit_to_merge),
        )
        repository.reset_to_commit(commit_to_merge, hard=True)
    else:
        taf_logger.info(
            "{} Commit {} already on branch {}",
            repository.name,
            format_commit(commit_to_merge),
            branch,
        )
