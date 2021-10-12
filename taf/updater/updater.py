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
from taf.auth_repo import AuthenticationRepository
import taf.settings as settings
from taf.exceptions import (
    ScriptExecutionError,
    UpdateFailedError,
    UpdaterAdditionalCommitsError,
    GitError,
    MissingHostsError,
    InvalidHostsError,
)
from taf.updater.handlers import GitUpdater
from taf.utils import on_rm_error
from taf.hosts import load_hosts_json, set_hosts_of_repo, load_hosts, get_hosts
from taf.updater.lifecycle_handlers import handle_repo_event, handle_host_event, Event


disable_tuf_console_logging()


class UpdateType(enum.Enum):
    TEST = "test"
    OFFICIAL = "official"
    EITHER = "either"


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


def _load_hosts_json(auth_repo):
    try:
        return load_hosts_json(auth_repo)
    except MissingHostsError as e:
        # if a there is no host file, the update should not fail
        taf_logger.info(str(e))
        return {}
    except InvalidHostsError as e:
        raise UpdateFailedError(str(e))


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


def update_repository(
    url,
    clients_auth_path,
    clients_library_dir=None,
    default_branch="main",
    update_from_filesystem=False,
    expected_repo_type=UpdateType.EITHER,
    target_repo_classes=None,
    target_factory=None,
    only_validate=False,
    validate_from_commit=None,
    error_if_unauthenticated=False,
    conf_directory_root=None,
    config_path=None,
    out_of_band_authentication=None,
    scripts_root_dir=None,
    checkout=True,
):
    """
    <Arguments>
    url:
        URL of the remote authentication repository
    clients_auth_path:
        Client's authentication repository's full path
    clients_library_dir:
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
    checkout:
        Whether to checkout last validated commits after update is done
    """
    # if the repository's name is not provided, divide it in parent directory
    # and repository name, since TUF's updater expects a name
    # but set the validate_repo_name setting to False
    clients_auth_path = Path(clients_auth_path).resolve()

    if clients_library_dir is None:
        clients_library_dir = clients_auth_path.parent.parent
    else:
        clients_library_dir = Path(clients_library_dir).resolve()

    auth_repo_name = f"{clients_auth_path.parent.name}/{clients_auth_path.name}"
    clients_auth_library_dir = clients_auth_path.parent.parent
    repos_update_data = {}
    transient_data = {}
    root_error = None
    try:
        _update_named_repository(
            url,
            clients_auth_library_dir,
            clients_library_dir,
            auth_repo_name,
            default_branch,
            update_from_filesystem,
            expected_repo_type,
            target_repo_classes,
            target_factory,
            only_validate,
            validate_from_commit,
            error_if_unauthenticated,
            conf_directory_root,
            repos_update_data=repos_update_data,
            transient_data=transient_data,
            out_of_band_authentication=out_of_band_authentication,
            scripts_root_dir=scripts_root_dir,
            checkout=checkout,
        )
    except Exception as e:
        root_error = e

    # after all repositories have been updated, sort them by hosts and call hosts handlers
    # update information is in repos_update_data
    if auth_repo_name not in repos_update_data:
        # this must mean that an error occurred
        if root_error is not None:
            raise root_error
        else:
            raise UpdateFailedError(f"Update of {auth_repo_name} failed")
    root_auth_repo = repos_update_data[auth_repo_name]["auth_repo"]
    repos_and_commits = {
        auth_repo_name: repo_data["commits_data"].get("after_pull")
        for auth_repo_name, repo_data in repos_update_data.items()
    }
    try:
        load_hosts(root_auth_repo, repos_and_commits)
    except InvalidHostsError as e:
        raise UpdateFailedError(str(e))

    hosts = get_hosts()
    host_update_status = Event.UNCHANGED
    errors = ""
    for host in hosts:
        # check if host update was successful - meaning that all repositories
        # of that host were updated successfully
        host_transient_data = {}
        for host_data in host.data_by_auth_repo.values():
            for host_repo_dict in host_data["auth_repos"]:
                for host_repo_name in host_repo_dict:
                    host_repo_update_data = repos_update_data[host_repo_name]
                    update_status = host_repo_update_data["update_status"]
                    if (
                        host_update_status != update_status
                        and host_update_status != Event.FAILED
                    ):
                        # if one failed, then failed
                        # else if one changed, then chenged
                        # else unchanged
                        host_update_status = update_status
                    repo_error = host_repo_update_data["error"]
                    if repo_error is not None:
                        errors += str(repo_error)
                if host_repo_name in transient_data:
                    host_transient_data[host_repo_name] = transient_data[host_repo_name]

        handle_host_event(
            host_update_status,
            host_transient_data,
            root_auth_repo.library_dir,
            scripts_root_dir,
            host,
            repos_update_data,
            errors,
        )
    if root_error:
        raise root_error


def _update_named_repository(
    url,
    clients_auth_library_dir,
    targets_library_dir,
    auth_repo_name,
    default_branch,
    update_from_filesystem,
    expected_repo_type,
    target_repo_classes=None,
    target_factory=None,
    only_validate=False,
    validate_from_commit=None,
    error_if_unauthenticated=False,
    conf_directory_root=None,
    visited=None,
    hosts_hierarchy_per_repo=None,
    repos_update_data=None,
    transient_data=None,
    out_of_band_authentication=None,
    scripts_root_dir=None,
    checkout=True,
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
        clients_auth_library_dir,
        targets_library_dir,
        auth_repo_name,
        default_branch,
        update_from_filesystem,
        expected_repo_type,
        target_repo_classes,
        target_factory,
        only_validate,
        validate_from_commit,
        error_if_unauthenticated,
        conf_directory_root,
        out_of_band_authentication,
        checkout,
    )

    # if commits_data is empty, do not attempt to load the host or dependencies
    # that can happen in the repository didn't exists, but could not be validated
    # and was therefore deleted
    # or if the last validated commit is not equal to the top commit, meaning that
    # the repository was updated without using the updater
    # this second case could be reworked to return the state as of the last validated commit
    # but treat the repository as invalid for now
    commits = []
    if commits_data["after_pull"] is not None:
        if hosts_hierarchy_per_repo is None:
            hosts_hierarchy_per_repo = {auth_repo.name: [_load_hosts_json(auth_repo)]}
        else:
            # some repositories might not contain hosts.json and their host is defined
            # in their parent authentication repository
            hosts_hierarchy_per_repo[auth_repo.name] += [_load_hosts_json(auth_repo)]

        if commits_data["before_pull"] is not None:
            commits = [commits_data["before_pull"]]
        commits.extend(commits_data["new"])
        # TODO
        # need to handle wrong definitions and make sure that the update doesn't fail
        # for now, just take the newest commit and do not worry about updated definitions
        # latest_commit = commits[-1::]
        repositoriesdb.load_dependencies(
            auth_repo,
            library_dir=targets_library_dir,
            commits=commits,
        )

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
                        clients_auth_library_dir,
                        targets_library_dir,
                        child_auth_repo.name,
                        default_branch,
                        False,
                        expected_repo_type,
                        target_repo_classes,
                        target_factory,
                        only_validate,
                        validate_from_commit,
                        error_if_unauthenticated,
                        conf_directory_root,
                        visited,
                        hosts_hierarchy_per_repo,
                        repos_update_data,
                        transient_data,
                        child_auth_repo.out_of_band_authentication,
                        scripts_root_dir=scripts_root_dir,
                        checkout=checkout,
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
        # TODO which commit to load if the commit top commit does not match the last validated commit
        # use last validated commit - if the repository contains it
        set_hosts_of_repo(auth_repo, hosts_hierarchy_per_repo[auth_repo.name])

        # all repositories that can be updated will be updated
        if not only_validate and len(commits) and update_status == Event.CHANGED:
            last_commit = commits[-1]
            # if there were no errors, merge the last validated authentication repository commit
            _merge_commit(auth_repo, auth_repo.default_branch, last_commit, checkout)
            # update the last validated commit
            auth_repo.set_last_validated_commit(last_commit)

        # do not call the handlers if only validating the repositories
        # if a handler fails and we are in the development mode, revert the update
        # so that it's easy to try again after fixing the handler
        if not only_validate:
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
    if error is not None:
        raise error


def _update_current_repository(
    url,
    clients_auth_library_dir,
    targets_library_dir,
    auth_repo_name,
    default_branch,
    update_from_filesystem,
    expected_repo_type,
    target_repo_classes,
    target_factory,
    only_validate,
    validate_from_commit,
    error_if_unauthenticated,
    conf_directory_root,
    out_of_band_authentication,
    checkout,
):
    settings.update_from_filesystem = update_from_filesystem
    settings.conf_directory_root = conf_directory_root
    settings.default_branch = default_branch
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
    tuf.settings.repositories_directory = clients_auth_library_dir

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
    except Exception as e:
        # Instantiation of the handler failed - this can happen if the url is not correct
        # of if the saved last validated commit does not match the current head commit
        # do not return any commits data if that is the case
        # TODO in case of last validated issue, think about returning commits up to the last validated one
        # the problem is that that could indicate that the history was changed
        users_auth_repo = AuthenticationRepository(
            clients_auth_library_dir,
            auth_repo_name,
            default_branch=default_branch,
            urls=[url],
            conf_directory_root=conf_directory_root,
        )
        # make sure that all update affects are deleted if the repository did not exist
        if not users_auth_repo.is_git_repository_root:
            shutil.rmtree(users_auth_repo.path, onerror=on_rm_error)
            shutil.rmtree(users_auth_repo.conf_dir)
        return Event.FAILED, users_auth_repo, _commits_ret(None, False, False), e, {}
    try:
        # the current authentication repository is instantiated in the handler
        users_auth_repo = repository_updater.update_handler.users_auth_repo
        existing_repo = users_auth_repo.is_git_repository_root
        additional_commits_per_repo = {}

        # this is the repository cloned inside the temp directory
        # we validate it before updating the actual authentication repository
        validation_auth_repo = repository_updater.update_handler.validation_auth_repo
        commits = repository_updater.update_handler.commits

        if (
            out_of_band_authentication is not None
            and users_auth_repo.last_validated_commit is None
            and commits[0] != out_of_band_authentication
        ):
            raise UpdateFailedError(
                f"First commit of repository {auth_repo_name} does not match "
                "out of band authentication commit"
            )
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
            library_dir=targets_library_dir,
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
            error_if_unauthenticated,
            checkout,
        )
    except Exception as e:
        if not existing_repo:
            shutil.rmtree(users_auth_repo.path, onerror=on_rm_error)
            shutil.rmtree(users_auth_repo.conf_dir)
            commits = None
        return (
            Event.FAILED,
            users_auth_repo,
            _commits_ret(commits, existing_repo, False),
            e,
            {},
        )
    finally:
        repository_updater.update_handler.cleanup()

    if error_if_unauthenticated and len(additional_commits_per_repo):
        return (
            Event.FAILED,
            users_auth_repo,
            _commits_ret(commits, existing_repo, False),
            UpdaterAdditionalCommitsError(additional_commits_per_repo),
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
                    )
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
            "Validation of authentication repository {} failed at revision {} due to error {}",
            users_auth_repo.name,
            current_commit,
            e,
        )
        raise UpdateFailedError(
            f"Validation of authentication repository {users_auth_repo.name}"
            f" failed at revision {current_commit} due to error: {e}"
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
    error_if_unauthenticated,
    checkout,
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
        # if unauthenticared commits are allowed, we also want to check if there are
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
                return [], {}
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
                if not allow_unauthenticated_for_repo:
                    repo_old_head = repository.top_commit_of_branch(branch)
                    if repo_old_head != old_head:
                        taf_logger.error(
                            "Mismatch between commits {} and {}",
                            old_head,
                            repo_old_head,
                        )
                        raise UpdateFailedError(
                            "Mismatch between target commits specified in authentication repository"
                            f" and target repository {repository.name} on branch {branch}"
                        )

            # the repository was cloned if it didn't exist
            # if it wasn't cloned, fetch the current branch
            new_commits_on_repo_branch = _get_commits(
                repository,
                is_git_repository,
                branch,
                only_validate,
                old_head,
                branch_exists,
                allow_unauthenticated_for_repo,
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
                    error_if_unauthenticated,
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
                    additional_commits_per_repo.get(path, {}).get(branch),
                    new_commits[path][branch],
                    checkout,
                )

    return additional_commits_per_repo, _set_target_repositories_data(
        repositories,
        repositories_branches_and_commits,
        top_commits_of_branches_before_pull,
        additional_commits_per_repo,
    )


def _get_commits(
    repository,
    existing_repository,
    branch,
    only_validate,
    old_head,
    branch_exists,
    allow_unauthenticated_commits,
):
    """Returns a list of newly fetched commits belonging to the specified branch."""
    if existing_repository:
        repository.fetch(branch=branch)

    if old_head is not None:
        if not only_validate:
            fetched_commits = repository.all_fetched_commits(branch=branch)
            if not allow_unauthenticated_commits:
                # if the local branch does not exist (the branch was not checked out locally)
                # fetched commits will include already validated commits
                # check which commits are newer that the previous head commit
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
                for commit in fetched_commits:
                    if commit not in new_commits_on_repo_branch:
                        new_commits_on_repo_branch.extend(fetched_commits)
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
    repository,
    branch,
    branch_commits,
    allow_unauthenticated,
    additional_commits,
    new_branch_commits,
    checkout=True,
):
    """Determines which commits needs to be merged into the specified branch and
    merge it.
    """
    if additional_commits is not None:
        allow_unauthenticated = False
    last_commit = branch_commits[-1]["commit"]

    last_validated_commit = last_commit
    commit_to_merge = (
        last_validated_commit if not allow_unauthenticated else new_branch_commits[-1]
    )
    taf_logger.info("Merging {} into {}", commit_to_merge, repository.name)
    _merge_commit(repository, branch, commit_to_merge, allow_unauthenticated, checkout)


def _merge_commit(
    repository, branch, commit_to_merge, allow_unauthenticated=False, checkout=True
):
    """Merge the specified commit into the given branch and check out the branch.
    If the repository cannot contain unauthenticated commits, check out the merged commit.
    """
    taf_logger.info("Merging commit {} into {}", commit_to_merge, repository.name)
    try:
        repository.checkout_branch(branch, raise_anyway=True)
    except GitError:
        # in order to merge a commit into a branch we need to check it out
        # but that cannot be done if it is checked out in a different worktree
        # it should be fine to update that other worktree if there are no uncommitted changes
        # or no commits that have not been pushed yet
        worktree = GitRepository(path=repository.find_worktree_path_by_branch(branch))
        if worktree is None:
            return False
        repository = worktree
        checkout = False

    repository.merge_commit(commit_to_merge)
    if checkout:
        if not allow_unauthenticated:
            repository.checkout_commit(commit_to_merge)
        else:
            repository.checkout_branch(branch)


def _set_target_repositories_data(
    repositories,
    repositories_branches_and_commits,
    top_commits_of_branches_before_pull,
    additional_commits_per_repo,
):
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
            if previous_top_of_branch is not None:
                # this needs to be the same - implementation error otherwise
                branch_commits_data["before_pull"] = commits_with_custom[0]
            else:
                branch_commits_data["before_pull"] = None
            branch_commits_data["after_pull"] = commits_with_custom[-1]
            if branch_commits_data["before_pull"] is not None:
                commits_with_custom.pop(0)
            branch_commits_data["new"] = commits_with_custom
            additional_commits = (
                additional_commits_per_repo[repo_name].get(branch, [])
                if repo_name in additional_commits_per_repo
                else []
            )
            branch_commits_data["unauthenticated"] = additional_commits
            commits_data[branch] = branch_commits_data
        targets_data[repo_name]["commits"] = commits_data
    return targets_data


def _update_target_repository(
    repository,
    new_commits,
    target_commits,
    allow_unauthenticated,
    branch,
    error_if_unauthenticated,
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
            f" and target repository {repository.name} on branch {branch}"
        )
    taf_logger.info("Successfully validated {}", repository.name)

    if error_if_unauthenticated and len(additional_commits):
        # these commits include all commits newer than last authenticated commit (if unauthenticated commits are allowed)
        # that does not necessarily mean that the local repository is not up to date with the remote
        # pull could've been run manually
        # check where the current local head is
        branch_current_head = repository.top_commit_of_branch(branch)
        if branch_current_head in additional_commits:
            additional_commits = additional_commits[
                additional_commits.index(branch_current_head) + 1 :
            ]

    return additional_commits


def validate_repository(
    clients_auth_path,
    clients_library_dir=None,
    default_branch="main",
    validate_from_commit=None,
):

    clients_auth_path = Path(clients_auth_path).resolve()

    if clients_library_dir is None:
        clients_library_dir = clients_auth_path.parent.parent
    else:
        clients_library_dir = Path(clients_library_dir).resolve()

    auth_repo_name = f"{clients_auth_path.parent.name}/{clients_auth_path.name}"
    clients_auth_library_dir = clients_auth_path.parent.parent
    expected_repo_type = (
        UpdateType.TEST
        if (clients_auth_path / "targets" / "test-auth-repo").exists()
        else UpdateType.OFFICIAL
    )
    _update_named_repository(
        str(clients_auth_path),
        clients_auth_library_dir,
        clients_library_dir,
        auth_repo_name,
        default_branch,
        True,
        expected_repo_type=expected_repo_type,
        only_validate=True,
        validate_from_commit=validate_from_commit,
    )
