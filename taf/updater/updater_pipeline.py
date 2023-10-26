from collections import defaultdict
import functools
from logging import ERROR, INFO
from pathlib import Path
import shutil
import tempfile
from typing import Any, Dict, List, Optional
from attr import attrs, define, field
from git import GitError
from logdecorator import log_on_end, log_on_error, log_on_start
from taf.git import GitRepository

import taf.settings as settings
import taf.repositoriesdb as repositoriesdb
from taf.auth_repo import AuthenticationRepository
from taf.exceptions import UpdateFailedError
from taf.updater.handlers import GitUpdater
from taf.updater.lifecycle_handlers import Event
from taf.updater.types.update import UpdateType
from taf.utils import on_rm_error
from taf.log import taf_logger
from tuf.ngclient.updater import Updater
from tuf.repository_tool import TARGETS_DIRECTORY_NAME


EXPIRED_METADATA_ERROR = "ExpiredMetadataError"
PROTECTED_DIRECTORY_NAME = "protected"
INFO_JSON_PATH = f"{TARGETS_DIRECTORY_NAME}/{PROTECTED_DIRECTORY_NAME}/info.json"


@define
class UpdateState:
    auth_commits_since_last_validated: List[Any] = field(factory=list)
    existing_repo: bool = field(default=False)
    update_successful: bool = field(default=False)
    event: Optional[str] = field(default=None)
    users_auth_repo: Optional["AuthenticationRepository"] = field(default=None)
    validation_auth_repo: Optional["AuthenticationRepository"] = field(default=None)
    auth_repo_name: Optional[str] = field(default=None)
    error: Optional[Exception] = field(default=None)
    targets_data: Dict[str, Any] = field(factory=dict)
    last_validated_commit: str = field(factory=str)
    target_repositories: Dict[str, "GitRepository"] = field(factory=dict)
    cloned_target_repositories: List["GitRepository"] = field(factory=list)
    target_branches_data_from_auth_repo: Dict = field(factory=dict)
    targets_data_by_auth_commits: Dict = field(factory=dict)
    old_heads_per_target_repos_branches: Dict[str, Dict[str, str]] = field(factory=dict)
    fetched_commits_per_target_repos_branches: Dict[str, Dict[str, List[str]]] = field(factory=dict)
    last_validated_commits_per_target_repos_branches: Dict[str, Dict[str, str]] = field(factory=dict)
    additional_commits_per_target_repos_branches: Dict[str, Dict[str, List[str]]] = field(factory=dict)


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
            if self.state.event == Event.FAILED and not self.state.existing_repo:
                shutil.rmtree(self.state.users_auth_repo.path, onerror=on_rm_error)
                shutil.rmtree(self.state.users_auth_repo.conf_dir)
    return wrapper


class Pipeline:

    def __init__(self, steps):
        self.steps = steps

    def run(self):
        for step in self.steps:
            try:
                should_continue = step()
                if not should_continue:
                    break

            except Exception as e:
                self._handle_error(e)
                break

            self._set_output()

    def _handle_error(self, e):
        pass

    def _set_output(self):
        pass

class AuthenticationRepositoryUpdatePipeline(Pipeline):


    def __init__(
        self, url, clients_auth_library_dir, targets_library_dir, auth_repo_name,
        update_from_filesystem, expected_repo_type, target_repo_classes, target_factory,
        only_validate, validate_from_commit, conf_directory_root, out_of_band_authentication,
        checkout, excluded_target_globs
    ):

        super().__init__(steps=[
            self.clone_remote_and_run_tuf_updater,
            self.validate_out_of_band_and_update_type,
            self.clone_or_fetch_users_auth_repo,
            self.load_target_repositories,
            self.clone_target_repositories_if_not_on_disk,
            self.get_targets_data_from_auth_repo,
            self.validate_target_repositories_initial_state,
            self.get_target_repositories_commits,
            self.validate_target_repositories,
            self.set_additional_commits_of_target_repositories,
            self.merge_branch_commits
        ])

        self.url = url
        self.clients_auth_library_dir = clients_auth_library_dir
        self.targets_library_dir = targets_library_dir
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
        self.state.auth_repo_name = auth_repo_name
        self.state.targets_data = {}
        self._output = None

    @property
    def output(self):
        if not self._output:
            raise ValueError("Pipeline has not been run yet. Please run the pipeline first.")
        return self._output

    @log_on_start(INFO, "Cloning repository and running TUF updater", logger=taf_logger)
    @log_on_end(INFO, "TUF validation finished", logger=taf_logger)
    @cleanup_decorator
    def clone_remote_and_run_tuf_updater(self):
        settings.update_from_filesystem = self.update_from_filesystem
        settings.conf_directory_root = self.conf_directory_root
        try:
            self.state.auth_commits_since_last_validated = None
            self.state.existing_repo = (
                Path(self.clients_auth_library_dir, self.state.auth_repo_name).exists()
                if self.state.auth_repo_name is not None
                else True
            )

            # Clone the validation repository in temp.
            self.state.auth_repo_name = _clone_validation_repo(self.url, self.state.auth_repo_name)
            git_updater = GitUpdater(self.url, self.clients_auth_library_dir, self.state.auth_repo_name)
            self.state.users_auth_repo = git_updater.users_auth_repo
            _run_tuf_updater(git_updater)
            self.state.existing_repo = self.state.users_auth_repo.is_git_repository_root
            self.state.validation_auth_repo = git_updater.validation_auth_repo
            self.state.auth_commits_since_last_validated = list(git_updater.commits)
            self.state.event = Event.CHANGED if len(self.state.auth_commits_since_last_validated) > 1 else Event.UNCHANGED

            # used for testing purposes
            if settings.overwrite_last_validated_commit:
                self.state.last_validated_commit = settings.last_validated_commit
            else:
                self.state.last_validated_commit = self.state.users_auth_repo.last_validated_commit
            # always clean up repository updater
            git_updater.cleanup()
            return True

        except Exception as e:
            self.state.error = e
            self.state.users_auth_repo = None

            if self.state.auth_repo_name is not None:
                self.state.users_auth_repo = AuthenticationRepository(
                    self.clients_auth_library_dir,
                    self.state.auth_repo_name,
                    urls=[self.url],
                    conf_directory_root=self.conf_directory_root,
                )
            self.state.event = Event.FAILED
            return False

    @cleanup_decorator
    @log_on_start(INFO, "Validating out of band commit and update type", logger=taf_logger)
    @log_on_end(INFO, "Validation finished", logger=taf_logger)
    def validate_out_of_band_and_update_type(self):
        try:
            # this is the repository cloned inside the temp directory
            # we validate it before updating the actual authentication repository
            if (
                self.out_of_band_authentication is not None
                and self.state.users_auth_repo.last_validated_commit is None
                and self.auth_commits_since_last_validated[0] != self.out_of_band_authentication
            ):
                raise UpdateFailedError(
                    f"First commit of repository {self.state.auth_repo_name} does not match "
                    "out of band authentication commit"
                )

            if self.expected_repo_type != UpdateType.EITHER:
                # check if the repository being updated is a test repository
                if self.state.validation_auth_repo.is_test_repo and self.expected_repo_type != UpdateType.TEST:
                    raise UpdateFailedError(
                        f"Repository {self.state.users_auth_repo.name} is a test repository. "
                        'Call update with "--expected-repo-type" test to update a test '
                        "repository"
                    )
                elif (
                    not self.state.validation_auth_repo.is_test_repo
                    and self.state.expected_repo_type == UpdateType.TEST
                ):
                    raise UpdateFailedError(
                        f"Repository {self.state.users_auth_repo.name} is not a test repository,"
                        ' but update was called with the "--expected-repo-type" test'
                    )
            return True
        except Exception as e:
            self.state.error = e
            self.state.event = Event.FAILED
            taf_logger.error(e)
            return False

    @log_on_start(INFO, "Cloning or updating user's authentication repository", logger=taf_logger)
    def clone_or_fetch_users_auth_repo(self):
        if not self.only_validate:
            # fetch the latest commit or clone the repository without checkout
            # do not merge before targets are validated as well
            try:
                if self.state.existing_repo:
                    self.state.users_auth_repo.fetch(fetch_all=True)
                else:
                    self.state.users_auth_repo.clone()
            except Exception as e:
                self.state.error = e
                self.state.event = Event.FAILED
                taf_logger.error(e)
                return False
        return True

    def load_target_repositories(self):
        try:
            repositoriesdb.load_repositories(
                self.state.users_auth_repo,
                repo_classes=self.target_repo_classes,
                factory=self.target_factory,
                library_dir=self.targets_library_dir,
                commits=self.state.auth_commits_since_last_validated,
                only_load_targets=False,
                excluded_target_globs=self.excluded_target_globs,
            )
            self.state.target_repositories = repositoriesdb.get_deduplicated_repositories(
                self.state.users_auth_repo, self.state.auth_commits_since_last_validated[-1::]
            )
            return True
        except Exception as e:
            self.state.error = e
            self.state.event = Event.FAILED
            taf_logger.error(e)
            return False

    @log_on_start(INFO, "Cloning target repositories which are not on disk", logger=taf_logger)
    @log_on_start(INFO, "Finished cloning target repositories", logger=taf_logger)
    def clone_target_repositories_if_not_on_disk(self):
        try:
            self.state.cloned_target_repositories = []
            for repository in self.state.target_repositories.values():
                is_git_repository = repository.is_git_repository_root
                if not is_git_repository:
                    if self.only_validate:
                        taf_logger.warning(
                            "Target repositories must already exist when only validating repositories"
                        )
                        continue
                    repository.clone(no_checkout=True)
                    self.state.cloned_target_repositories.append(repository)
            return True
        except Exception as e:
            self.state.error = e
            self.state.event = Event.FAILED
            taf_logger.error(e)
            return False


    def get_targets_data_from_auth_repo(self):
        self.state.targets_data_by_auth_commits = self.state.users_auth_repo.targets_data_by_auth_commits(self.state.auth_commits_since_last_validated)
        repo_branches = {}
        for repo_name, commits_data in  self.state.targets_data_by_auth_commits.items():
            branches = set()  # using a set to avoid duplicate branches
            for commit_data in commits_data.values():
                branches.add(commit_data["branch"])
            repo_branches[repo_name] = sorted(list(branches))
        self.state.target_branches_data_from_auth_repo = repo_branches
        return True


    @log_on_start(INFO, "Validating initial state of target repositories", logger=taf_logger)
    def validate_target_repositories_initial_state(self):
        try:
            self.state.old_heads_per_target_repos_branches = defaultdict(dict)
            for repo_name, repository in self.target_repositories:
                for branch in self.state.target_branches_data_from_auth_repo[repo_name]:
                    # if last_validated_commit is None or if the target repository didn't exist prior
                    # to calling update, start the update from the beginning
                    # otherwise, for each branch, start with the last validated commit of the local branch
                    branch_exists = repository.branch_exists(branch, include_remotes=False)
                    if not branch_exists and self.only_validate:
                        self.state.targets_data = {}
                        msg = f"{repo_name} does not contain a local branch named {branch} and cannot be validated. Please update the repositories"
                        taf_logger.error(msg)
                        raise UpdateFailedError(msg)

                    # TODO
                    repo_branch_commits = []
                    if (
                        self.last_validated_commit is None
                        or not repository.is_git_repository_root
                        or not branch_exists
                        or not len(repo_branch_commits)
                    ):
                        old_head = None
                    else:
                        old_head = repo_branch_commits[0]
                        if not _is_unauthenticated_allowed(repository):
                            repo_old_head = repository.top_commit_of_branch(branch)
                            # do the same as when checking the top and last_validated_commit of the authentication repository
                            if repo_old_head != old_head:
                                commits_since = repository.all_commits_since_commit(old_head)
                                if repo_old_head not in commits_since:
                                    msg = f"Top commit of repository {repository.name} {repo_old_head} and is not equal to or newer than commit defined in auth repo {old_head}"
                                    taf_logger.error(msg)
                                    raise UpdateFailedError(msg)
                    self.state.old_heads_per_target_repos_branches[repo_name][branch] = old_head
            return True
        except Exception as e:
            self.state.error = e
            self.state.event = Event.FAILED
            taf_logger.error(e)
            # TODO remove cloned?
            return False

    @log_on_start(INFO, "Validating initial state of target repositories", logger=taf_logger)
    def get_target_repositories_commits(self):
        """Returns a list of newly fetched commits belonging to the specified branch."""
        self.state.fetched_commits_per_target_repos_branches = defaultdict(dict)
        for repo_name, repository in self.target_repositories:
            for branch in self.state.target_branches_data_from_auth_repo[repo_name]:
                if repository.is_git_repository_root:
                    repository.fetch(branch=branch)

                old_head = self.state.old_heads_per_target_repos_branches[repo_name][branch]
                if old_head is not None:
                    if not self.only_validate:
                        fetched_commits = repository.all_commits_on_branch(
                            branch=f"origin/{branch}"
                        )

                        # if the local branch does not exist (the branch was not checked out locally)
                        # fetched commits will include already validated commits
                        # check which commits are newer that the previous head commit
                        if old_head in fetched_commits:
                            fetched_commits_on_target_repo_branch = fetched_commits[
                                fetched_commits.index(old_head) + 1 : :
                            ]
                        else:
                            fetched_commits_on_target_repo_branch = repository.all_commits_since_commit(
                                old_head, branch
                            )
                            for commit in fetched_commits:
                                if commit not in fetched_commits_on_target_repo_branch:
                                    fetched_commits_on_target_repo_branch.append(commit)
                    else:
                        fetched_commits_on_target_repo_branch = repository.all_commits_since_commit(
                            old_head, branch
                        )
                    fetched_commits_on_target_repo_branch.insert(0, old_head)
                else:
                    branch_exists = repository.branch_exists(branch, include_remotes=False)
                    if branch_exists:
                        # this happens in the case when last_validated_commit does not exist
                        # we want to validate all commits, so combine existing commits and
                        # fetched commits
                        fetched_commits_on_target_repo_branch = repository.all_commits_on_branch(
                            branch=branch, reverse=True
                        )
                    else:
                        fetched_commits_on_target_repo_branch = []
                    if not self.only_validate:
                        try:
                            fetched_commits = repository.all_commits_on_branch(
                                branch=f"origin/{branch}"
                            )

                            # if the local branch does not exist (the branch was not checked out locally)
                            # fetched commits will include already validated commits
                            # check which commits are newer that the previous head commit
                            for commit in fetched_commits:
                                if commit not in fetched_commits_on_target_repo_branch:
                                    fetched_commits_on_target_repo_branch.append(commit)
                        except GitError:
                            pass
                self.state.fetched_commits_per_target_repos_branches[repo_name][branch] = fetched_commits_on_target_repo_branch
        return True

    @log_on_start(INFO, "Validating target repositories...", logger=taf_logger)
    def validate_target_repositories(self):
        """
        Breadth-first update of target repositories
        Merge last valid commits at the end of the update
        """
        try:
            last_validated_target_commits_per_repositories = {}
            self.state.last_validated_commits_per_target_repos_branches = defaultdict(dict)
            for auth_commit in self.state.auth_commits_since_last_validated:
                for repository in self.state.target_repositories.values():
                    last_validated_target_commit = last_validated_target_commits_per_repositories.get(repository.name)
                    current_targets_data_from_auth_repo = self.state.targets_data_by_auth_commits[repository.name][auth_commit]
                    target_commits_from_target_repo = self.state.fetched_commits_per_target_repos_branches[repository.name]
                    validated_commit = self._validate_current_repo_commit(
                        repository,
                        self.state.users_auth_repo,
                        last_validated_target_commit,
                        current_targets_data_from_auth_repo,
                        target_commits_from_target_repo,
                        auth_commit)
                    last_validated_target_commits_per_repositories[repository.name] = validated_commit
            return True
        # TODO merge until the last validated
        # if at some point validation fails
        except Exception as e:
            self.state.error = e
            self.state.event = Event.FAILED
            return False


        # self.state.even = Event.CHANGED if len(self.state.auth_commits_since_last_validated) > 1 else Event.UNCHANGED
        # TODO set targets_data
        # return (
        #     event,
        #     users_auth_repo,
        #     auth_repo_name,
        #     _commits_ret(commits, existing_repo, True),
        #     None,
        #     targets_data,
        # )

    def _validate_current_repo_commit(
            self,
            repository,
            users_auth_repo,
            last_validated_target_commit,
            current_targets_data_from_auth_repo,
            target_commits_from_target_repo,
            current_auth_commit,
        ):
        current_commit_from_auth_repo = current_targets_data_from_auth_repo["commit"]
        branch = current_targets_data_from_auth_repo["branch"]
        target_commits_from_target_repos_on_branch = target_commits_from_target_repo[branch]
        if last_validated_target_commit is not None and last_validated_target_commit in target_commits_from_target_repos_on_branch:
            # same branch
            current_target_commit = _find_next_value(last_validated_target_commit, target_commits_from_target_repos_on_branch)
        else:
            # next branch
            current_target_commit = target_commits_from_target_repos_on_branch[0]

        if current_target_commit is None:
            # there are commits missing from the target repository
            commit_date = users_auth_repo.get_commit_date()
            raise UpdateFailedError(
                f"Failure to validate {users_auth_repo.name} commit {current_auth_commit} committed on {commit_date}:\
                    data repository {repository.name} was supposed to be at commit {current_commit_from_auth_repo} \
                    but commit not on branch {branch}"
            )

        current_target_commit = target_commits_from_target_repo[branch].index
        if current_commit_from_auth_repo == current_target_commit:
            self.state.last_validated_commits_per_target_repos_branches[repository.name][branch] = current_target_commit
            return current_target_commit
        if not _is_unauthenticated_allowed(repository):
            commit_date = users_auth_repo.get_commit_date()
            raise UpdateFailedError(
                f"Failure to validate {users_auth_repo.name} commit {current_auth_commit} committed on {commit_date}:\
                    data repository {repository.name} was supposed to be at commit {current_commit_from_auth_repo} \
                    but repo was at {last_validated_target_commit}"
            )
        # unauthenticated commits are allowed, try to skip them
        # if commits of the target repositories were swapped, commit which is expected to be found
        # after the current one will be skipped and it won't be found later, so validation will fail
        remaining_commits = target_commits_from_target_repos_on_branch[target_commits_from_target_repos_on_branch.index(last_validated_target_commit):]
        for target_commit in remaining_commits:
            if current_commit_from_auth_repo == target_commit:
                self.state.last_validated_commits_per_target_repos_branches[repository.name][branch] = target_commit
                return target_commit
            taf_logger.info(f"{repository.name}: skipping target commit {target_commit}. Looking for commit {current_commit_from_auth_repo}")
        raise UpdateFailedError(
            f"Failure to validate {users_auth_repo.name} commit {current_auth_commit} committed on {commit_date}:\
                data repository {repository.name} was supposed to be at commit {current_commit_from_auth_repo} \
                but commit not on branch {branch}"
        )

    def set_additional_commits_of_target_repositories(self):
        """
        For target repository and for each branch, extract commits following the last validated commit
        These commits are not invalid. In case of repositories which cannot contain unauthenticated commits
        all of these commits will have to get signed if at least one commits on that branch needs to get signed
        However, no error will get reported if there are commits which have not yet been signed
        In case of repositories which can contain unauthenticated commits, they do not even need to get signed
        """
        self.state.additional_commits_per_target_repos_branches = defaultdict(dict)
        for repository in self.state.target_repositories.values():
            # this will only include branches who were, at least partially, validated (up until a certain point)
            for branch, last_validated_commit in self.state.last_validated_commits_per_target_repos_branches[repository.name].items():
                # TODO what to do if an error occurred while validating that branch
                branch_commits = self.state.fetched_commits_per_target_repos_branches[repository.name][branch]
                additional_commits = branch_commits[branch_commits.index(last_validated_commit) + 1:]
                if len(additional_commits):
                    taf_logger.info(f"Repository {repository.name}: found commits succeeding the last authenticated commit on branch {branch}: {','.join(additional_commits)}")

                    # these commits include all commits newer than last authenticated commit (if unauthenticated commits are allowed)
                    # that does not necessarily mean that the local repository is not up to date with the remote
                    # pull could've been run manually
                    # check where the current local head is
                    # TODO I don't remember why this was done!
                    branch_current_head = repository.top_commit_of_branch(branch)
                    if branch_current_head in additional_commits:
                        additional_commits = additional_commits[
                            additional_commits.index(branch_current_head) + 1 :
                        ]
                self.state.additional_commits_per_target_repos_branches[repository.name][branch] = additional_commits
        return True

    @log_on_start(INFO, "Merging commits into target repositories...", logger=taf_logger)
    def merge_commits(self):
        """Determines which commits needs to be merged into the specified branch and
        merge it.
        """
        try:
            if self.only_validate:
                return
            for repository in self.state.target_repositories.values():
                # this will only include branches who were, at least partially, validated (up until a certain point)
                for branch, last_validated_commit in self.state.last_validated_commits_per_target_repos_branches[repository.name].items():
                    commit_to_merge = (
                        last_validated_commit if not _is_unauthenticated_allowed(repository) else self.state.fetched_commits_per_target_repos_branches[repository.name][branch][-1]
                )
                    taf_logger.info("Repository {}: merging {} into branch {}",  repository.name, commit_to_merge, branch)
                    _merge_commit(repository, branch, commit_to_merge)
            return True
        except Exception as e:
            self.state.error = e
            self.state.event = Event.FAILED
            return False

    def set_target_repositories_data(self):
        # targets_data = {}
        # for repo_name, repo in repositories.items():
        #     targets_data[repo_name] = {"repo_data": repo.to_json_dict()}
        #     commits_data = {}
        #     for branch, commits_with_custom in repositories_branches_and_commits[
        #         repo_name
        #     ].items():
        #         branch_commits_data = {}
        #         previous_top_of_branch = top_commits_of_branches_before_pull[repo_name][
        #             branch
        #         ]

        #         branch_commits_data["before_pull"] = None

        #         if previous_top_of_branch is not None:
        #             # this needs to be the same - implementation error otherwise
        #             branch_commits_data["before_pull"] = (
        #                 commits_with_custom[0] if len(commits_with_custom) else None
        #             )

        #         branch_commits_data["after_pull"] = (
        #             commits_with_custom[-1] if len(commits_with_custom) else None
        #         )

        #         if branch_commits_data["before_pull"] is not None:
        #             commits_with_custom.pop(0)
        #         branch_commits_data["new"] = commits_with_custom
        #         additional_commits = (
        #             additional_commits_per_repo[repo_name].get(branch, [])
        #             if repo_name in additional_commits_per_repo
        #             else []
        #         )
        #         branch_commits_data["unauthenticated"] = additional_commits
        #         commits_data[branch] = branch_commits_data
        #     targets_data[repo_name]["commits"] = commits_data
        # return targets_data
        pass



    def merge_branch_commits(self):
        # Implement logic
        # Update self.state as necessary
        pass



    def handle_error(self, error):
        # Centralized error handling
        print(f"Error encountered: {error}")


    def _set_output(self):
        if self.state.auth_commits_since_last_validated is None:
            commit_before_pull = None
            new_commits = []
            commit_after_pull = None
        else:
            commit_before_pull = self.state.auth_commits_since_last_validated[0] if self.state.existing_repo and len(self.state.auth_commits_since_last_validated) else None
            commit_after_pull = self.state.auth_commits_since_last_validated[-1] if self.state.update_successful else self.state.auth_commits_since_last_validated[0]

            if not self.state.existing_repo:
                new_commits = self.state.auth_commits_since_last_validated
            else:
                new_commits = self.state.auth_commits_since_last_validated[1:] if len(self.state.auth_commits_since_last_validated) else []
        commits_data = {
            "before_pull": commit_before_pull,
            "new": new_commits,
            "after_pull": commit_after_pull,
        }
        self._output = UpdateOutput(
            event=self.state.event,
            users_auth_repo=self.state.users_auth_repo,
            auth_repo_name=self.state.auth_repo_name,
            commits_data=commits_data,
            error=self.state.error,
            targets_data=self.state.targets_data
        )


def _clone_validation_repo(url, repository_name):
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

    validation_head_sha = validation_auth_repo.top_commit_of_branch(
        validation_auth_repo.default_branch
    )

    if repository_name is None:
        try:
            info = validation_auth_repo.get_json(validation_head_sha, INFO_JSON_PATH)
            repository_name = f'{info["namespace"]}/{info["name"]}'
        except Exception:
            raise UpdateFailedError(
                "Error during info.json parse. When specifying --clients-library-dir check if info.json metadata exists in targets/protected or provide full path to auth repo"
            )

    validation_auth_repo.cleanup()
    return repository_name

def _is_unauthenticated_allowed(repository):
    return repository.custom.get(
        "allow-unauthenticated-commits", False
    )

@log_on_start(INFO, "Running TUF validation of the authentication repository...", logger=taf_logger)
def _run_tuf_updater(git_updater):
    def _init_updater():
        try:
            return Updater(
                git_updater.metadata_dir,
                "metadata/",
                git_updater.targets_dir,
                "targets/",
                fetcher=git_updater,
            )
        except Exception as e:
            taf_logger.error(f"Failed to instantiate TUF Updater due to error: {e}")
            raise e

    def _update_tuf_current_revision():
        current_commit = git_updater.current_commit
        try:
            updater.refresh()
            taf_logger.debug("Validated metadata files at revision {}", current_commit)
            # using refresh, we have updated all main roles
            # we still need to update the delegated roles (if there are any)
            # and validate any target files
            current_targets = git_updater.get_current_targets()
            for target_path in current_targets:
                target_filepath = target_path.replace("\\", "/")

                targetinfo = updater.get_targetinfo(target_filepath)
                target_data = git_updater.get_current_target_data(
                    target_filepath, raw=True
                )
                targetinfo.verify_length_and_hashes(target_data)

                taf_logger.debug(
                    "Successfully validated target file {} at {}",
                    target_filepath,
                    current_commit,
                )
        except Exception as e:
            metadata_expired = EXPIRED_METADATA_ERROR in type(
                e
            ).__name__ or EXPIRED_METADATA_ERROR in str(e)
            if not metadata_expired or settings.strict:
                taf_logger.error(
                    "Validation of authentication repository {} failed at revision {} due to error: {}",
                    git_updater.users_auth_repo.name,
                    current_commit,
                    e,
                )
                raise UpdateFailedError(
                    f"Validation of authentication repository {git_updater.users_auth_repo.name}"
                    f" failed at revision {current_commit} due to error: {e}"
                )
            taf_logger.warning(
                f"WARNING: Could not validate authentication repository {git_updater.users_auth_repo.name} at revision {current_commit} due to error: {e}"
            )

    while not git_updater.update_done():
        updater = _init_updater()
        _update_tuf_current_revision()

    taf_logger.info(
        "Successfully validated authentication repository {}",
        git_updater.users_auth_repo.name,
    )


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

def _merge_commit(self, repository, branch, commit_to_merge, checkout=True):
    """Merge the specified commit into the given branch and check out the branch.
    If the repository cannot contain unauthenticated commits, check out the merged commit.
    """
    taf_logger.info("Merging commit {} into {}", commit_to_merge, repository.name)
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

    repository.merge_commit(commit_to_merge)
    if checkout:
        taf_logger.info("{}: checking out branch {}", repository.name, branch)
        repository.checkout_branch(branch)
