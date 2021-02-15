import json
import shutil
import enum

import tuf
import tuf.client.updater as tuf_updater

from collections import defaultdict
from pathlib import Path
from taf.log import taf_logger, disable_tuf_console_logging
from taf.git import GitRepository
import taf.repositoriesdb as repositoriesdb
from taf.auth_repo import NamedAuthenticationRepo
import taf.settings as settings
from taf.exceptions import UpdateFailedError, UpdaterAdditionalCommits, GitError
from taf.updater.handlers import GitUpdater
from taf.utils import on_rm_error
from taf.hosts import load_hosts_json, set_hosts_of_repo
from taf.updater.lifecycle_handlers import handle_repo_event, Event


disable_tuf_console_logging()

# TODO
# make sure custom info is loaded from dependencies.json
# checge additional info to custom everywhere
# validate initial commit based on auth-of-band-authentication which should be moved out of custom data

class UpdateType(enum.Enum):
    TEST = 1
    OFFICIAL = 2
    EITHER = 3

    @classmethod
    def from_name(cls, name):
        update_type = {v: k for k, v in UPDATE_TYPES.items()}.get(name)
        if update_type is not None:
            return update_type
        raise ValueError("{} is not a valid update type".format(name))

    def to_name(self):
        return UPDATE_TYPES[self.value]


UPDATE_TYPES = {
    UpdateType.TEST: "test",
    UpdateType.OFFICIAL: "official",
    UpdateType.EITHER: "either",
}


# TODO config path should be configurable
def load_library_context(config_path):
    config = {}
    config_path = Path(config_path)
    try:
        config = json.loads(config_path.read_text())
    except json.JSONDecodeError:
        taf_logger.warning("Invalid json in config file at {}", str(config_path))
    except FileNotFoundError:
        taf_logger.warning("No config found at {}", str(config_path))
    return config


def prepare_host_script_data(auth_repo, auth_repo_head, config_path):
    """
        {

        last_successful_commits: {

        },

        config: {

        },

        hosts: {

        }
    }
    """
    data = {
        "last_successful_commits": auth_repo.last_successful_commmits,
        "auth_repo_head": auth_repo_head,
        "config": load_library_context(config_path),
        "hosts": auth_repo.hosts,
    }
    return json.dumps(data)


def update_repository(
    url,
    clients_auth_path,
    clients_root_dir=None,
    update_from_filesystem=False,
    expected_repo_type=UpdateType.EITHER,
    target_repo_classes=None,
    target_factory=None,
    only_validate=False,
    validate_from_commit=None,
    check_for_unauthenticated=False,
    conf_directory_root=None,
    config_path=None,
):
    """
    <Arguments>
    url:
        URL of the remote authentication repository
    clients_auth_path:
        Client's authentication repository's full path
    clients_root_dir:
        Directory where client's target repositories are located.
    update_from_filesystem:
        A flag which indicates if the URL is actually a file system path
    expected_repo_type:
        Indicates if the authentication repository which needs to be updated is
        a test repository, official repository, or if the type is not important
        and should not be validated
    target_repo_classes:
        A class or a dictionary used when instantiating target repositories.
        See repositoriesdb load_repositories for more details.
    target_factory:
        A git repositories factory used when instantiating target repositories.
        See repositoriesdb load_repositories for more details.
    """
    # if the repository's name is not provided, divide it in parent directory
    # and repository name, since TUF's updater expects a name
    # but set the validate_repo_name setting to False
    clients_auth_path = Path(clients_auth_path).resolve()

    if clients_root_dir is None:
        clients_root_dir = clients_auth_path.parent.parent
    else:
        clients_root_dir = Path(clients_root_dir).resolve()

    auth_repo_name = f"{clients_auth_path.parent.name}/{clients_auth_path.name}"
    clients_auth_root_dir = clients_auth_path.parent.parent
    repos_update_succeeded = {}
    hosts = (
        {}
    )  # store host name and all information about the repositories; model as a new class
    try:
        _update_named_repository(
            url,
            clients_auth_root_dir,
            clients_root_dir,
            auth_repo_name,
            update_from_filesystem,
            expected_repo_type,
            target_repo_classes,
            target_factory,
            only_validate,
            validate_from_commit,
            check_for_unauthenticated,
            conf_directory_root,
            repos_update_succeeded=repos_update_succeeded,
        )
    except Exception:
        pass


def _update_named_repository(
    url,
    clients_auth_root_dir,
    targets_root_dir,
    auth_repo_name,
    update_from_filesystem,
    expected_repo_type=UpdateType.EITHER,
    target_repo_classes=None,
    target_factory=None,
    only_validate=False,
    validate_from_commit=None,
    check_for_unauthenticated=False,
    conf_directory_root=None,
    visited=None,
    hosts_hierarchy_per_repo=None,
    repos_update_succeeded=None,
):
    """
    <Arguments>
        url:
        URL of the remote authentication repository
        clients_directory:
        Directory where the client's authentication repository is located
        repo_name:
        Name of the authentication repository. Can be namespace prefixed
        targets_dir:
        Directory where the target repositories are located
        update_from_filesystem:
        A flag which indicates if the URL is actually a file system path
        authenticate_test_repo:
        A flag which indicates that the repository to be updated is a test repository
        target_repo_classes:
        A class or a dictionary used when instantiating target repositories.
        See repositoriesdb load_repositories for more details.
        target_factory:
        A git repositories factory used when instantiating target repositories.
        See repositoriesdb load_repositories for more details.

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
    The 'GitMetadataUpdater' updater is designed in such a way that for each new call it
    loads data from a most recent commit.
    """
    if visited is None:
        visited = []
    # if there is a recursive dependency
    if auth_repo_name in visited:
        return
    visited.append(auth_repo_name)

    # at the moment, we assume that the initial commit is valid and that it contains at least root.json
    (
        update_status,
        auth_repo,
        commits_data,
        error,
        targets_data,
    ) = _update_current_repository(
        url,
        clients_auth_root_dir,
        targets_root_dir,
        auth_repo_name,
        update_from_filesystem,
        expected_repo_type=UpdateType.EITHER,
        target_repo_classes=None,
        target_factory=None,
        only_validate=False,
        validate_from_commit=None,
        check_for_unauthenticated=False,
        conf_directory_root=None,
        addtional_repo_data=None,
    )

    # check if top repository
    if hosts_hierarchy_per_repo is None:
        hosts_hierarchy_per_repo = {auth_repo.name: [load_hosts_json(auth_repo)]}
    else:
        try:
            # some repositories might not contain hosts.json and their host is defined
            # in their parent authentication repository
            hosts_hierarchy_per_repo[auth_repo.name] += [load_hosts_json(auth_repo)]
        except Exception:
            pass

    commits = []
    if commits_data["before_pull"] is not None:
        commits = [commits_data["before_pull"]]
    commits.extend(commits_data["new"])
    repositoriesdb.load_dependencies(
        auth_repo,
        root_dir=targets_root_dir,
        commits=commits,
    )

    # TODO log what happened
    if update_status != Event.FAILED:
        errors = []
        # load the repositories from dependencies.json and update these repositories
        # we need to update the repositories before loading hosts data
        child_auth_repos = repositoriesdb.get_deduplicated_auth_repositories(
            auth_repo, commits
        ).values()
        for child_auth_repo in child_auth_repos:
            hosts_hierarchy_per_repo[child_auth_repo.name] = list(
                hosts_hierarchy_per_repo[auth_repo.name]
            )
            try:
                _update_named_repository(
                    child_auth_repo.urls[0],
                    clients_auth_root_dir,
                    targets_root_dir,
                    child_auth_repo.name,
                    False,
                    expected_repo_type,
                    target_repo_classes,
                    target_factory,
                    only_validate,
                    validate_from_commit,
                    check_for_unauthenticated,
                    conf_directory_root,
                    visited,
                    hosts_hierarchy_per_repo,
                    repos_update_succeeded,
                )
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

    set_hosts_of_repo(auth_repo, hosts_hierarchy_per_repo[auth_repo.name])

    # all repositories that can be updated will be updated
    if not only_validate and len(commits) and update_status == Event.CHANGED:
        last_commit = commits[-1]
        taf_logger.info("Merging commit {} into {}", last_commit, auth_repo.name)
        # if there were no errors, merge the last validated authentication repository commit
        _merge_commit(auth_repo, auth_repo.default_branch, last_commit)
        # update the last validated commit
        auth_repo.set_last_validated_commit(last_commit)

    # TODO
    # combine auth repo data with commits and use that to form auth_data
    # implement to/from json
    handle_repo_event(update_status, auth_repo, commits_data, error, targets_data)
    repos_update_succeeded[auth_repo.name] = update_status != Event.FAILED
    if error is not None:
        raise error
    # TODO export targets data
    # validation of the repository finished - successfully or not


def _update_current_repository(
    url,
    clients_auth_root_dir,
    targets_root_dir,
    auth_repo_name,
    update_from_filesystem,
    expected_repo_type=UpdateType.EITHER,
    target_repo_classes=None,
    target_factory=None,
    only_validate=False,
    validate_from_commit=None,
    check_for_unauthenticated=False,
    conf_directory_root=None,
    addtional_repo_data=None,
):
    settings.update_from_filesystem = update_from_filesystem
    settings.conf_directory_root = conf_directory_root
    if only_validate:
        settings.overwrite_last_validated_commit = True
        settings.last_validated_commit = validate_from_commit
    # instantiate TUF's updater
    repository_mirrors = {
        "mirror1": {
            "url_prefix": url,
            "metadata_path": "metadata",
            "targets_path": "targets",
            "confined_target_dirs": [""],
        }
    }
    tuf.settings.repositories_directory = clients_auth_root_dir

    def _commits_ret(commits, existing_repo, update_successful):
        if commits is None:
            commit_before_pull = None
            new_commits = []
            commit_after_pull = None
        else:
            commit_before_pull = commits[0] if existing_repo and len(commits) else None
            commit_after_pull = commits[-1] if update_successful else commits[0]
            new_commits = commits[1:] if len(commits) else []
        return {
            "before_pull": commit_before_pull,
            "new": new_commits,
            "after_pull": commit_after_pull,
        }

    try:
        commits = None
        repository_updater = tuf_updater.Updater(
            auth_repo_name, repository_mirrors, GitUpdater
        )
        # the current authentication repository is insantiated in the handler
        users_auth_repo = repository_updater.update_handler.users_auth_repo

        existing_repo = users_auth_repo.is_git_repository_root
        additional_commits_per_repo = {}

        # this is the repository cloned inside the temp directory
        # we validate it before updating the actual authentication repository
        validation_auth_repo = repository_updater.update_handler.validation_auth_repo
        commits = repository_updater.update_handler.commits

    except Exception as e:
        users_auth_repo = NamedAuthenticationRepo(
            clients_auth_root_dir,
            auth_repo_name,
            urls=[url],
            conf_directory_root=conf_directory_root,
        )
        if commits is not None:
            return (
                Event.FAILED,
                users_auth_repo,
                _commits_ret(commits, existing_repo, False),
                e,
                {},
            )
        # this can happen if instantiation of the handler failed
        # that will happen if the last successful commit is not the same as the top commit of the
        # repository
        # do not return any commits data in that case
        return Event.FAILED, users_auth_repo, _commits_ret(commits, False, False), e, {}
    try:
        # used for testing purposes
        if settings.overwrite_last_validated_commit:
            last_validated_commit = settings.last_validated_commit
        else:
            last_validated_commit = users_auth_repo.last_validated_commit

        if expected_repo_type != UpdateType.EITHER:
            # check if the repository being updated is a test repository
            targets = validation_auth_repo.get_json(
                commits[-1], "metadata/targets.json"
            )
            test_repo = "test-auth-repo" in targets["signed"]["targets"]
            if test_repo and expected_repo_type != UpdateType.TEST:
                raise UpdateFailedError(
                    f"Repository {users_auth_repo.name} is a test repository. "
                    'Call update with "--expected-repo-type" test to update a test '
                    "repository"
                )
            elif not test_repo and expected_repo_type == UpdateType.TEST:
                raise UpdateFailedError(
                    f"Repository {users_auth_repo.name} is not a test repository,"
                    ' but update was called with the "--expected-repo-type" test'
                )

        # validate the authentication repository and fetch new commits
        # if the validation is completed successfully, new commits are fetched (not merged yet)
        _update_authentication_repository(repository_updater, only_validate)

        # load target repositories and validate them
        repositoriesdb.load_repositories(
            users_auth_repo,
            repo_classes=target_repo_classes,
            factory=target_factory,
            root_dir=targets_root_dir,
            commits=commits,
        )
        repositories = repositoriesdb.get_deduplicated_repositories(
            users_auth_repo, commits
        )
        repositories_branches_and_commits = (
            users_auth_repo.sorted_commits_and_branches_per_repositories(commits)
        )

        additional_commits_per_repo, targets_data = _update_target_repositories(
            repositories,
            repositories_branches_and_commits,
            last_validated_commit,
            only_validate,
            check_for_unauthenticated,
        )
    except Exception as e:
        if not existing_repo:
            shutil.rmtree(users_auth_repo.path, onerror=on_rm_error)
            shutil.rmtree(users_auth_repo.conf_dir)
        return (
            Event.FAILED,
            users_auth_repo,
            _commits_ret(commits, existing_repo, False),
            e,
            {},
        )
    finally:
        repository_updater.update_handler.cleanup()
        repositoriesdb.clear_repositories_db()

    if check_for_unauthenticated and len(additional_commits_per_repo):
        return (
            Event.FAILED,
            users_auth_repo,
            _commits_ret(commits, existing_repo, False),
            UpdaterAdditionalCommits(additional_commits_per_repo),
            {},
            {},
        )

    # commits list will always contain the previous top commit of the repository
    event = Event.CHANGED if len(commits) > 1 else Event.UNCHANGED
    return (
        event,
        users_auth_repo,
        _commits_ret(commits, existing_repo, True),
        None,
        targets_data,
    )


def _update_authentication_repository(repository_updater, only_validate):

    users_auth_repo = repository_updater.update_handler.users_auth_repo
    taf_logger.info("Validating authentication repository {}", users_auth_repo.name)
    try:
        while not repository_updater.update_handler.update_done():
            current_commit = repository_updater.update_handler.current_commit
            repository_updater.refresh()
            # using refresh, we have updated all main roles
            # we still need to update the delegated roles (if there are any)
            # that is handled by get_current_targets
            current_targets = repository_updater.update_handler.get_current_targets()
            taf_logger.debug("Validated metadata files at revision {}", current_commit)
            for target_path in current_targets:
                target = repository_updater.get_one_valid_targetinfo(target_path)
                target_filepath = target["filepath"]
                trusted_length = target["fileinfo"]["length"]
                trusted_hashes = target["fileinfo"]["hashes"]
                try:
                    repository_updater._get_target_file(
                        target_filepath, trusted_length, trusted_hashes
                    )  # pylint: disable=W0212 # noqa
                except tuf.exceptions.NoWorkingMirrorError as e:
                    taf_logger.error("Could not validate file {}", target_filepath)
                    raise e
                taf_logger.debug(
                    "Successfully validated target file {} at {}",
                    target_filepath,
                    current_commit,
                )
    except Exception as e:
        # for now, useful for debugging
        taf_logger.error(
            "Validation of authentication repository {} failed due to error {}",
            users_auth_repo.name,
            e,
        )
        raise UpdateFailedError(
            f"Validation of authentication repository {users_auth_repo.name}"
            f" failed due to error: {e}"
        )

    taf_logger.info(
        "Successfully validated authentication repository {}", users_auth_repo.name
    )

    if not only_validate:
        # fetch the latest commit or clone the repository without checkout
        # do not merge before targets are validated as well
        if users_auth_repo.is_git_repository_root:
            users_auth_repo.fetch(fetch_all=True)
        else:
            users_auth_repo.clone(no_checkout=True)


def _update_target_repositories(
    repositories,
    repositories_branches_and_commits,
    last_validated_commit,
    only_validate,
    check_for_unauthenticated,
):
    taf_logger.info("Validating target repositories")
    # keep track of the repositories which were cloned
    # so that they can be removed if the update fails
    cloned_repositories = []
    allow_unauthenticated = {}
    new_commits = defaultdict(dict)
    additional_commits_per_repo = {}
    top_commits_of_branches_before_pull = {}
    for path, repository in repositories.items():
        taf_logger.info("Validating repository {}", repository.name)
        allow_unauthenticated_for_repo = repository.custom.get(
            "allow-unauthenticated-commits", False
        )
        allow_unauthenticated[path] = allow_unauthenticated_for_repo
        is_git_repository = repository.is_git_repository_root
        if not is_git_repository:
            if only_validate:
                taf_logger.info(
                    "Target repositories must already exist when only validating repositories"
                )
                continue
            repository.clone(no_checkout=True)
            cloned_repositories.append(repository)

        # if no commits were published, repositories_branches_and_commits will be empty
        # if unauthenticared commits are allow, we also want to check if there are
        # new commits which
        # only check the default branch
        if (
            not len(repositories_branches_and_commits[path])
            and allow_unauthenticated_for_repo
            and not only_validate
        ):
            repositories_branches_and_commits[path][repository.default_branch] = []
        for branch in repositories_branches_and_commits[path]:
            taf_logger.info("Validating branch {}", branch)
            # if last_validated_commit is None or if the target repository didn't exist prior
            # to calling update, start the update from the beggining
            # otherwise, for each branch, start with the last validated commit of the local
            # branch
            branch_exists = repository.branch_exists(branch, include_remotes=False)
            if not branch_exists and only_validate:
                taf_logger.error(
                    "{} does not contain a local branch named {} and cannot be validated. Please update the repositories",
                    repository.name,
                    branch,
                )
                return
            repo_branch_commits = repositories_branches_and_commits[path][branch]
            repo_branch_commits = [
                commit_info["commit"] for commit_info in repo_branch_commits
            ]
            if (
                last_validated_commit is None
                or not is_git_repository
                or not branch_exists
                or not len(repo_branch_commits)
            ):
                old_head = None
            else:
                # TODO what if a local target repository is missing some commits,
                # but all existing commits are valid?
                # top commit of any branch should be identical to commit sha
                # defined for that branch in commit which was the top commit
                # of the authentication repository's master branch at the time
                # of update's invocation
                old_head = repo_branch_commits[0]

            # the repository was cloned if it didn't exist
            # if it wasn't cloned, fetch the current branch
            new_commits_on_repo_branch = _get_commits(
                repository,
                is_git_repository,
                branch,
                only_validate,
                old_head,
                branch_exists,
            )
            top_commits_of_branches_before_pull.setdefault(path, {})[branch] = old_head
            new_commits[path].setdefault(branch, []).extend(new_commits_on_repo_branch)
            try:
                additional_commits_on_branch = _update_target_repository(
                    repository,
                    new_commits_on_repo_branch,
                    repo_branch_commits,
                    allow_unauthenticated_for_repo,
                    branch,
                    check_for_unauthenticated,
                )
                if len(additional_commits_on_branch):
                    additional_commits_per_repo.setdefault(repository.name, {})[
                        branch
                    ] = additional_commits_on_branch

            except UpdateFailedError as e:
                taf_logger.error("Updated failed due to error {}", str(e))
                # delete all repositories that were cloned
                for repo in cloned_repositories:
                    taf_logger.debug("Removing cloned repository {}", repo.path)
                    shutil.rmtree(repo.path, onerror=on_rm_error)
                # TODO is it important to undo a fetch if the repository was not cloned?
                raise e

    taf_logger.info("Successfully validated all target repositories.")
    if not only_validate:
        # if update is successful, merge the commits
        for path, repository in repositories.items():
            for branch in repositories_branches_and_commits[path]:
                branch_commits = repositories_branches_and_commits[path][branch]
                if not len(branch_commits):
                    continue
                _merge_branch_commits(
                    repository,
                    branch,
                    branch_commits,
                    allow_unauthenticated[path],
                    new_commits[path][branch],
                )

    return additional_commits_per_repo, _set_target_repositories_data(
        repositories,
        repositories_branches_and_commits,
        top_commits_of_branches_before_pull,
        additional_commits_per_repo,
    )


def _get_commits(
    repository, existing_repository, branch, only_validate, old_head, branch_exists
):
    if existing_repository:
        repository.fetch(branch=branch)
    if old_head is not None:
        if not only_validate:
            # if the local branch does not exist (the branch was not checked out locally)
            # fetched commits will include already validated commits
            # check which commits are newer that the previous head commit
            fetched_commits = repository.all_fetched_commits(branch=branch)
            if old_head in fetched_commits:
                new_commits_on_repo_branch = fetched_commits[
                    fetched_commits.index(old_head) + 1 : :
                ]
            else:
                new_commits_on_repo_branch = fetched_commits
        else:
            new_commits_on_repo_branch = repository.all_commits_since_commit(
                old_head, branch
            )
        new_commits_on_repo_branch.insert(0, old_head)
    else:
        if branch_exists:
            # this happens in the case when last_validated_commit does not exist
            # we want to validate all commits, so combine existing commits and
            # fetched commits
            new_commits_on_repo_branch = repository.all_commits_on_branch(
                branch=branch, reverse=True
            )
        else:
            new_commits_on_repo_branch = []
        if not only_validate:
            try:
                fetched_commits = repository.all_fetched_commits(branch=branch)
                # if the local branch does not exist (the branch was not checked out locally)
                # fetched commits will include already validated commits
                # check which commits are newer that the previous head commit
                for commit in fetched_commits:
                    if commit not in new_commits_on_repo_branch:
                        new_commits_on_repo_branch.extend(fetched_commits)
            except GitError:
                pass
    return new_commits_on_repo_branch


def _merge_branch_commits(
    repository, branch, branch_commits, allow_unauthenticated, new_branch_commits
):
    last_commit = branch_commits[-1]["commit"]
    last_validated_commit = last_commit
    commit_to_merge = (
        last_validated_commit if not allow_unauthenticated else new_branch_commits[-1]
    )
    taf_logger.info("Merging {} into {}", commit_to_merge, repository.name)
    _merge_commit(repository, branch, commit_to_merge, allow_unauthenticated)


def _merge_commit(repository, branch, commit_to_merge, allow_unauthenticated=False):
    checkout = True
    try:
        repository.checkout_branch(branch, raise_anyway=True)
    except GitError:
        # in order to merge a commit into a branch we need to check it out
        # but that cannot be done if it is checked out in a different worktree
        # it should be fine to update that other worktree if there are no uncommitted changes
        # or no commits that have not been pushed yet
        worktree = GitRepository(repository.find_worktree_path_by_branch(branch))
        if worktree is None:
            return False
        repository = worktree
        checkout = False

    repository.merge_commit(commit_to_merge)
    if checkout:
        if not allow_unauthenticated:
            repository.checkout_commit(commit_to_merge)
        else:
            repository.checkout_branch(repository.default_branch)


def _set_target_repositories_data(
    repositories,
    repositories_branches_and_commits,
    top_commits_of_branches_before_pull,
    additional_commits_per_repo,
):
    # TODO figure out what to return if pull failed
    # the problem is that the pull could've failed because the commits weren't the same
    # as those specified in auth repo
    targets_data = {}
    for repo_name, repo in repositories.items():
        targets_data[repo_name] = {"repo_data": repo.to_json_dict()}
        commits_data = {}
        for branch, commits_with_custom in repositories_branches_and_commits[
            repo_name
        ].items():
            branch_commits_data = {}
            previous_top_of_branch = top_commits_of_branches_before_pull[repo_name][
                branch
            ]
            # should not be empty if exists
            assert len(commits_with_custom)
            if previous_top_of_branch is not None:
                # this needs to be the same - implementation error otherwise
                assert previous_top_of_branch == commits_with_custom[0]["commit"]
                branch_commits_data["before_pull"] = commits_with_custom[0]
            else:
                branch_commits_data["before_pull"] = None
            branch_commits_data["after_pull"] = commits_with_custom[-1]
            if branch_commits_data["before_pull"] is not None:
                commits_with_custom.pop(0)
            branch_commits_data["new"] = commits_with_custom
            additional_commits = (
                additional_commits_per_repo.get(branch, [])
                if repo_name in additional_commits_per_repo
                else []
            )
            branch_commits_data["unathenticated"] = additional_commits
            commits_data[branch] = branch_commits_data
        targets_data[repo_name]["commits"] = commits_data
    return targets_data


def _update_target_repository(
    repository,
    new_commits,
    target_commits,
    allow_unauthenticated,
    branch,
    check_for_unauthenticated,
):
    taf_logger.info(
        "Validating target repository {} {} branch", repository.name, branch
    )
    # if authenticated commits are allowed, return a list of all fetched commits which
    # are newer tham the last authenticated commits
    additional_commits = []
    # A new commit might have been pushed after the update process
    # started and before fetch was called
    # So, the number of new commits, pushed to the target repository, could
    # be greater than the number of these commits according to the authentication
    # repository. The opposite cannot be the case.
    # In general, if there are additional commits in the target repositories,
    # the updater will finish the update successfully, but will only update the
    # target repositories until the latest validated commit
    if not allow_unauthenticated:
        update_successful = len(new_commits) >= len(target_commits)
        if update_successful:
            for target_commit, repo_commit in zip(target_commits, new_commits):
                if target_commit != repo_commit:
                    taf_logger.error(
                        "Mismatch between commits {} and {}", target_commit, repo_commit
                    )
                    update_successful = False
                    break
        if len(new_commits) > len(target_commits):
            additional_commits = new_commits[len(target_commits) :]
            taf_logger.warning(
                "Found commits {} in repository {} that are not accounted for in the authentication repo."
                "Repository will be updated up to commit {}",
                additional_commits,
                repository.name,
                target_commits[-1],
            )
    else:
        taf_logger.info(
            "Unauthenticated commits allowed in repository {}", repository.name
        )
        update_successful = False
        if not len(target_commits):
            update_successful = True
            additional_commits = new_commits
        else:
            target_commits_index = 0
            for new_commit_index, commit in enumerate(new_commits):
                if commit in target_commits:
                    if commit != target_commits[target_commits_index]:
                        taf_logger.error(
                            "Mismatch between commits {} and {}",
                            commit,
                            target_commits[target_commits_index],
                        )
                        break
                    else:
                        target_commits_index += 1
                if commit == target_commits[-1]:
                    update_successful = True
                    if commit != new_commits[-1]:
                        additional_commits = new_commits[new_commit_index + 1 :]
                    break
            if len(additional_commits):
                taf_logger.warning(
                    "Found commits {} in repository {} which are newer than the last authenticable commit."
                    "Repository will be updated up to commit {}",
                    additional_commits,
                    repository.name,
                    commit,
                )

    if not update_successful:
        taf_logger.error(
            "Mismatch between target commits specified in authentication repository and the "
            "target repository {}",
            repository.name,
        )
        raise UpdateFailedError(
            "Mismatch between target commits specified in authentication repository"
            f" and target repository {repository.name}"
        )
    taf_logger.info("Successfully validated {}", repository.name)

    if check_for_unauthenticated and len(additional_commits):
        # these commits include all commits newer than last authenticated commit (if unauthenticated commits are allowed)
        # that does not necessarily mean that the local repository is not up to date with the remote on
        # pull could've been run manually
        # check where the current local head is
        branch_current_head = repository.top_commit_of_branch(branch)
        additional_commits = additional_commits[
            additional_commits.index(branch_current_head) + 1 :
        ]

    return additional_commits


def validate_repository(
    clients_auth_path, clients_root_dir=None, validate_from_commit=None
):

    clients_auth_path = Path(clients_auth_path).resolve()

    if clients_root_dir is None:
        clients_root_dir = clients_auth_path.parent.parent
    else:
        clients_root_dir = Path(clients_root_dir).resolve()

    auth_repo_name = f"{clients_auth_path.parent.name}/{clients_auth_path.name}"
    clients_auth_root_dir = clients_auth_path.parent.parent
    expected_repo_type = (
        UpdateType.TEST
        if (clients_auth_path / "targets" / "test-auth-repo").exists()
        else UpdateType.OFFICIAL
    )
    _update_named_repository(
        str(clients_auth_path),
        clients_auth_root_dir,
        clients_root_dir,
        auth_repo_name,
        True,
        expected_repo_type=expected_repo_type,
        only_validate=True,
        validate_from_commit=validate_from_commit,
    )
