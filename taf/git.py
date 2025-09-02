from __future__ import annotations
import datetime
import json
import itertools
import os
import re
import shutil
import uuid
import pygit2
import subprocess
import logging
from collections import OrderedDict
from functools import partial, reduce
from pathlib import Path

import requests  # type: ignore
from taf.models.types import Commitish
import taf.settings as settings
from taf.exceptions import (
    GitAccessDeniedException,
    NoRemoteError,
    NothingToCommitError,
    PushFailedError,
    TAFError,
    CloneRepoException,
    FetchException,
    InvalidRepositoryError,
    GitError,
    UpdateFailedError,
    PygitError,
)
from taf.log import NOTICE, taf_logger
from taf.utils import run
from typing import Callable, Dict, List, Optional, Tuple, Union
from .pygit import PyGitRepository

EMPTY_TREE = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"


class GitRepository:
    def __init__(
        self,
        library_dir: Optional[Union[Path, str]] = None,
        name: Optional[str] = None,
        urls: Optional[List[str]] = None,
        custom: Optional[Dict] = None,
        default_branch: Optional[str] = None,
        allow_unsafe: Optional[bool] = False,
        path: Optional[Union[Path, str]] = None,
        alias: Optional[str] = None,
        *args,
        **kwargs,
    ):
        """
        Args:
          library_dir (Path or str): path to the library root. This is a directory which contains other repositories,
          whose full path is determined by appending their names to the library dir. A repository can be
          instantiated by specifying library dir and name, or by the full path.
          name (str): repository's name, which is appended to the library dir to form the full path.
          Must be in the namespace/name format. If library_dir is specified, name must be specified too.
          path (Path): repository's full filesystem path, which can be specified instead of name and library dir
          urls (list): repository's urls
          custom (dict): a dictionary containing other data
          default_branch (str): repository's default branch, automatically determined if not specified
          allow_unsafe: allow a git's security mechanism which prevents execution of git commands if
          the containing directory is owned by a different user to be ignored
          alias: Repository's alias, which will be used in logging statements to reference it
        """
        if isinstance(library_dir, str):
            library_dir = Path(library_dir)
        if isinstance(path, str):
            path = Path(path)

        if (library_dir, name).count(None) == 1:
            raise InvalidRepositoryError(
                "Both library_dir and name need to be specified"
            )
        if name is not None and library_dir is not None:
            self.name = self._validate_repo_name(name)
            self.path = self._validate_repo_path(library_dir, name, path)
            self.library_dir = library_dir.expanduser().resolve()
        elif path is None:
            raise InvalidRepositoryError(
                "Either specify library dir and name pair or path!"
            )
        else:
            # maintain support for repositories whose names are not of significance
            # in that case, only full path is specified (can happen if only using the GitRepository class)
            # without the rest of the framework in some cotext
            # name is still required for logging, so determine it based on the path
            # if the path points to a direcotry directly inside the root direcotry
            # set name to the name of that folder
            # otherwise, use the same format that is expected when name is specified
            if path.parent.parent != path.parent:
                self.name = f"{path.parent.name}/{path.name}"
                self.library_dir = path.parent.parent
            else:
                self.name = path.name
                self.library_dir = path.parent
            self.library_dir = self.library_dir.resolve()
            self.path = self._validate_repo_path(path)

        self.alias = alias
        self.urls = self._validate_urls([str(url) for url in urls]) if urls else None
        self.allow_unsafe = allow_unsafe
        self.custom = custom or {}
        if default_branch is None:
            default_branch = self._determine_default_branch()
        self.default_branch = default_branch

    _pygit = None

    @property
    def pygit(self):
        if self._pygit is None:
            if not self.is_git_repository:
                raise GitError(
                    self,
                    message=f"The path '{self.path.as_posix()}' is not a Git repository.",
                )
            try:
                self._pygit = PyGitRepository(self)
                if not self._pygit:
                    raise PygitError("PyGitRepository instance is None")

            except Exception as e:
                error_message = f"Failed to instantiate PyGitRepository: {e}"
                logging.error(error_message)
                raise PygitError(error_message)
        return self._pygit

    @classmethod
    def from_json_dict(cls, json_data: Dict):
        """Create a new instance based on data contained by the `json_data` dictionary,
        which can be create by calling `to_json_dict`
        """
        return cls(**json_data)

    def to_json_dict(self):
        """Returns a dictionary mapping all attributes to their values"""
        return {
            "library_dir": str(self.library_dir),
            "name": self.name,
            "urls": self.urls,
            "default_branch": self.default_branch,
            "custom": self.custom,
        }

    logging_functions = {
        logging.DEBUG: taf_logger.debug,
        logging.INFO: taf_logger.info,
        NOTICE: partial(taf_logger.log, "NOTICE"),
        logging.WARNING: taf_logger.warning,
        logging.ERROR: taf_logger.error,
        logging.CRITICAL: taf_logger.critical,
    }

    log_template = "{}{}"

    _remotes = None

    _is_bare_repo = None

    @property
    def remotes(self) -> List[str]:
        if self._remotes is None:
            repo = self.pygit_repo
            if repo is None:
                return []
            self._remotes = [remote.name for remote in repo.remotes]
        return self._remotes

    @property
    def is_detached_head(self) -> bool:
        repo = self.pygit_repo
        return repo.head_is_detached

    @property
    def is_git_repository(self) -> bool:
        """Check if the given path is the root of a Git repository."""
        # This is used when instantiating a PyGitRepository repo, so do not use
        # it here
        try:
            result = self._git("rev-parse --is-inside-work-tree", reraise_error=True)
            if result == "true":
                return True
            result = self._git("rev-parse --is-bare-repository", reraise_error=True)
            if result == "true":
                return True

        except GitError:
            return False
        return False

    @property
    def is_git_repository_root(self) -> bool:
        try:
            if not self.is_git_repository:
                return False
            repo = self.pygit_repo
            if repo is None:
                return False
            if self.is_bare_repository:
                return repo.is_bare and Path(repo.path).resolve() == self.path.resolve()
            else:
                git_path = self.path / ".git"
                return Path(repo.path).resolve() == git_path.resolve() and (
                    git_path.is_dir() or git_path.is_file()
                )
        except PygitError:
            return False

    @property
    def initial_commit(self) -> Commitish:
        return (
            Commitish.from_hash(
                self._git(
                    "rev-list --max-parents=0 HEAD", error_if_not_exists=False
                ).strip()
            )
            if self.is_git_repository
            else None
        )

    @property
    def log_prefix(self) -> str:
        if self.alias:
            return f"{self.alias}: "
        return f"Repo {self.name}: "

    @property
    def pygit_repo(self) -> pygit2.Repository:
        if self.pygit.repo is None:
            raise PygitError("Failed to instantiate PyGitRepository")
        return self.pygit.repo

    @property
    def is_bare_repository(self) -> bool:
        if self._is_bare_repo is None:
            if self.pygit_repo is not None:
                self._is_bare_repo = self.pygit_repo.is_bare
            else:
                raise GitError(
                    "Cannot determine if repository is a bare repository. Cannot instantiate pygit repository"
                )

        return self._is_bare_repo

    def _git(self, cmd, *args, **kwargs):
        """Call git commands in subprocess
        e.g.:
          self._git('checkout {}', branch_name)
        """
        log_error = kwargs.pop("log_error", False)
        log_error_msg = kwargs.pop("log_error_msg", "")
        reraise_error = kwargs.pop("reraise_error", False)
        log_success_msg = kwargs.pop("log_success_msg", "")
        error_if_not_exists = kwargs.pop("error_if_not_exists", True)

        if len(args):
            cmd = cmd.format(*args)
        if self.allow_unsafe:
            command = f"git -C {self.path} -c safe.directory={self.path} {cmd}"
        else:
            command = f"git -C {self.path} {cmd}"
        result = None
        if log_error or log_error_msg:
            try:
                result = run(command, **kwargs)
                if log_success_msg:
                    self._log_debug(log_success_msg)
            except subprocess.CalledProcessError as e:
                if error_if_not_exists and (
                    not self.path.is_dir() or not self.is_git_repository
                ):
                    log_error_msg = (
                        f"{self.path} does not exist or is not a git repository"
                    )
                    reraise_error = True
                if log_error_msg:
                    error = GitError(self, message=log_error_msg, error=e)
                    self._log_error(error.message)
                else:
                    error = GitError(self, command=command, error=e)
                    # not every git error indicates a problem
                    # if it does, we expect that either custom error message will be provided
                    # or that the error will be reraised
                    self._log_debug(error.message)
                if reraise_error:
                    raise error
        else:
            try:
                result = run(command, **kwargs)
            except subprocess.CalledProcessError as e:
                raise GitError(self, command=command, error=e)
            if log_success_msg:
                self._log_debug(log_success_msg)
        return result

    def _get_default_branch_from_local(self) -> str:
        """
        Get the default branch from the local repository.
        Try to get the default branch from `refs/remotes/origin/HEAD` first.

        In a repository where the refs/remotes/origin/HEAD does not exist, this error will trigger:
            fatal: ref refs/remotes/origin/HEAD is not a symbolic ref

        In those cases, get the default branch from `git remote show origin`.

        If the repository does not have a remote set, use `symbolic-ref` HEAD
        """
        try:
            branch = self._git(
                "symbolic-ref refs/remotes/origin/HEAD --short", reraise_error=True
            )
            return _local_branch_re.sub("", branch)
        except GitError as e:
            self._log_debug(f"Could not get remote HEAD at {self.path}: {e}")
            pass
        try:
            result = self._git("remote show origin", reraise_error=True)
            match = re.search(r"HEAD branch:(.*)", result)
            if match is not None:
                return match.group(1).strip()
        except (GitError, IndexError) as e:
            self._log_debug(
                f"Could not get HEAD branch with git remote show origin at {self.path}: {e}"
            )
            pass
        try:
            return self._git("symbolic-ref HEAD --short", reraise_error=True)
        except GitError as e:
            self._log_debug(f"Could not get HEAD branch at {self.path}: {e}")
            pass
        raise GitError(
            self,
            message="Could not determine default branch from local repository",
        )

    def _get_default_branch_from_remote(self, url: str) -> str:
        if not self.is_git_repository:
            raise GitError(
                self,
                message="Could not get default branch from remote. Not a git repository",
            )
        branch = self._git(
            f"ls-remote --symref {url} HEAD",
            log_error=True,
            log_error_msg="Unable to get default branch from remote",
            reraise_error=True,
        )
        branch = branch.split("\t", 1)[0]
        branch = branch.split()[-1]
        return _remote_branch_re.sub("", branch)

    def _log(self, log_func: Callable, message: str) -> None:
        log_func(self.log_template, self.log_prefix, message)

    def _log_debug(self, message: str) -> None:
        self._log(self.logging_functions[logging.DEBUG], message)

    def _log_info(self, message: str) -> None:
        self._log(self.logging_functions[logging.INFO], message)

    def _log_notice(self, message: str) -> None:
        self._log(self.logging_functions[NOTICE], message)

    def _log_warning(self, message: str) -> None:
        self._log(self.logging_functions[logging.WARNING], message)

    def _log_error(self, message: str) -> None:
        self._log(self.logging_functions[logging.ERROR], message)

    def _log_critical(self, message: str) -> None:
        self._log(self.logging_functions[logging.CRITICAL], message)

    def all_commits_on_branch(
        self, branch: Optional[str] = None, reverse: Optional[bool] = True
    ) -> List[Commitish]:
        """Returns a list of all commits on the specified branch.
        If branch is None, all commits on the currently checked out branch will be returned
        """
        repo = self.pygit_repo

        if branch:
            branch_obj = repo.branches.get(branch)
            if branch_obj is None:
                raise GitError(
                    self,
                    message=f"Error occurred while getting commits of branch {branch}. Branch does not exist",
                )
            latest_commit_id = branch_obj.target
        else:
            if self.head_commit() is None:
                raise GitError(
                    self,
                    message=f"Error occurred while getting commits of branch {branch}. No HEAD reference",
                )
            latest_commit_id = repo[repo.head.target].id

        sort = pygit2.GIT_SORT_REVERSE if reverse else pygit2.GIT_SORT_NONE
        commits = [
            Commitish.from_hash(commit.id.hex)
            for commit in repo.walk(latest_commit_id, sort)
        ]
        self._log_debug(
            f"found the following commits: {', '.join([commit.value for commit in commits])}"
        )
        return commits

    def all_commits_since_commit(
        self,
        since_commit: Optional[Commitish] = None,
        branch: Optional[str] = None,
        reverse: Optional[bool] = True,
    ) -> List[Commitish]:
        """Returns a list of all commits since the specified commit on the
        specified or currently checked out branch

        Raises:
            exceptions.GitError: An error occurred with provided commit SHA
        """

        if since_commit is None:
            try:
                return self.all_commits_on_branch(branch=branch, reverse=reverse)
            except GitError as e:
                self._log_warning(str(e))
                return []

        try:
            self.commit_exists(commit=since_commit)
        except GitError as e:
            self._log_warning(f"Commit {since_commit} not found in local repository.")
            raise e
        repo = self.pygit_repo

        if branch:
            branch_obj = repo.branches.get(branch)
            if branch_obj is None:
                return []
            latest_commit_id = branch_obj.target
        else:
            if self.head_commit() is None:
                return []
            latest_commit_id = repo[repo.head.target].id

        if repo.descendant_of(since_commit.hash, latest_commit_id):
            return []

        commits: List[Commitish] = []
        for commit in repo.walk(latest_commit_id):
            commit = Commitish.from_hash(commit.id.hex)
            if commit == since_commit:
                break
            commits.insert(0, commit)

        if not reverse:
            commits = commits[::-1]
        self._log_debug(
            f"found the following commits: {', '.join([commit.value for commit in commits])}"
        )
        return commits

    def add_remote(
        self, upstream_name: str, upstream_url: str, raise_error_if_exists=False
    ) -> None:
        try:
            if self.remote_exists(upstream_name):
                if raise_error_if_exists:
                    raise GitError(
                        self, message=f"Remote {upstream_name} already exists"
                    )
                return
            self._git("remote add {} {}", upstream_name, upstream_url)
            if self._remotes:
                self._remotes.append(upstream_name)
        except GitError as e:
            if "already exists" not in str(e):
                raise

    def branches(
        self, remote: bool = False, all: bool = False, strip_remote: bool = False
    ) -> List[str]:
        """Returns all branches."""
        repo = self.pygit_repo

        if all:
            branches = set(repo.branches)
        elif remote:
            branches = set(repo.branches.remote)
        else:
            branches = set(repo.branches.local)

        if strip_remote:
            remotes = self.remotes
            branches = set(
                [
                    reduce(lambda b, r: b.replace(f"{r}/", ""), remotes, branch)
                    for branch in branches
                ]
            )

        return list(branches)

    def branches_containing_commit(
        self,
        commit: Commitish,
        strip_remote: Optional[bool] = False,
        sort_key: Optional[Callable] = None,
    ) -> OrderedDict:
        """Finds all branches that contain the given commit"""
        repo = self.pygit_repo

        local_branches = remote_branches = []
        try:
            local_branches = list(repo.branches.local.with_commit(commit.hash))
        except pygit2.GitError:
            pass
        try:
            remote_branches = list(repo.branches.remote.with_commit(commit.hash))
        except pygit2.GitError:
            pass
        filtered_remote_branches = []
        if len(remote_branches):
            for branch in remote_branches:
                local_name = self.branch_local_name(branch)
                if (
                    local_name
                    and "HEAD" not in local_name
                    and local_name not in local_branches
                ):
                    if strip_remote:
                        branch = self.branch_local_name(branch)
                    filtered_remote_branches.append(branch)
        branches = {branch: False for branch in local_branches}
        branches.update({branch: True for branch in filtered_remote_branches})
        return OrderedDict(sorted(branches.items(), key=sort_key, reverse=True))

    def branch_exists(
        self, branch_name: str, include_remotes: Optional[bool] = True
    ) -> bool:
        """
        Checks if a branch with the given name exists.
        If include_remotes is set to True, this checks if
        a remote branch exists.
        """
        repo = self.pygit_repo

        branch = repo.branches.get(branch_name)
        # this git command should return the branch's name if it exists
        # empty string otherwise
        if branch is not None:
            return True
        if include_remotes:
            for remote in self.remotes:
                remote_branch = repo.branches.remote.get(f"{remote}/{branch_name}")
                if remote_branch is not None:
                    return remote_branch

                # finally, check remote branch
                if self.has_remote():
                    return branch_name in self._git(
                        f"ls-remote --heads origin {branch_name}",
                        log_error_msg=f"Repo {self.name}: could check if the branch exists in the remote repository",
                        reraise_error=True,
                    )

        return False

    def branch_off_commit(self, branch_name: str, commit: Commitish) -> None:
        """Create a new branch by branching off of the specified commit"""
        repo = self.pygit_repo

        try:
            pygit2_commit = repo[commit.hash]
            repo.branches.local.create(branch_name, pygit2_commit)
            branch = repo.lookup_branch(branch_name)
            ref = repo.lookup_reference(branch.name)
            repo.checkout(ref)
        except Exception as e:
            self._log_error(str(e))
            raise
        finally:
            self._log_info(
                f"Created a new branch {branch_name} from branching off of {commit}"
            )

    def branch_local_name(self, remote_branch_name: str) -> Optional[str]:
        """Strip remote from the given remote branch"""
        for remote in self.remotes:
            if remote_branch_name.startswith(remote + "/"):
                return remote_branch_name.split("/", 1)[1]
        return None

    def checkout_branch(
        self,
        branch_name: str,
        create: Optional[bool] = False,
        raise_anyway: bool = False,
    ) -> None:
        """Check out the specified branch. If it does not exists and
        the create parameter is set to True, create a new branch.
        If the branch does not exist and create is set to False,
        raise an exception."""
        repo = self.pygit_repo

        try:
            branch = repo.lookup_branch(branch_name)
            if branch is not None:
                ref = repo.lookup_reference(branch.name)
                repo.checkout(ref)
            else:
                self._git(
                    "checkout {}",
                    branch_name,
                    log_success_msg=f"Repo {self.name}: checked out branch {branch_name}",
                )
        except Exception as e:
            if raise_anyway:
                raise GitError(repo=self, message=str(e))
            # skip worktree errors
            if "the current HEAD of a linked repository" in str(e):
                return

            if create:
                self.create_and_checkout_branch(branch_name)
            else:
                self._log_error(f"could not checkout branch {branch_name}")
                raise (e)

    def check_if_clean_and_synced(self, branch: Optional[str] = None) -> bool:
        """
        Check if repository's worktree is clean and if the
        specified (or default) branch is synced with remote
        (if the repository has a remote set)
        """
        branch = branch or self.default_branch
        if self.something_to_commit():
            return False
        if not self.has_remote():
            return True
        if not self.synced_with_remote(branch):
            return False
        return True

    def checkout_paths(self, commit: Commitish, *args) -> None:
        repo = self.pygit_repo

        pygit_commit = repo.get(commit.hash)
        repo.checkout_tree(
            pygit_commit, paths=list(args), strategy=pygit2.GIT_CHECKOUT_FORCE
        )

    def checkout_orphan_branch(self, branch_name: str) -> None:
        """Creates orphan branch"""
        self._git(
            f"checkout --orphan {branch_name}", log_error=True, reraise_error=True
        )
        try:
            self._git("rm -rf .")
        except GitError:  # If repository is empty
            pass

    def check_files_exist(
        self, file_paths: List[str], commit: Optional[Commitish] = None
    ):
        """
        Check if file paths are known to git
        """
        existing_files: list = []
        non_existing: list = []
        repo = self.pygit_repo

        if commit is None:
            commit = self.head_commit()

        if commit is None:
            return existing_files, non_existing

        pygit_commit = repo[commit.hash]
        tree = pygit_commit.tree  # Get the tree of that commit

        for file_path in file_paths:
            try:
                # Check if the file exists in the tree
                tree[file_path]
                existing_files.append(file_path)
            except KeyError:
                non_existing.append(file_path)

        return existing_files, non_existing

    def clean(self):
        self._git("clean -fd")

    def cleanup(self):
        if self._pygit is not None:
            self._pygit.cleanup()
            self._pygit = None

    def clean_and_reset(self):
        """Cleans the untracked files and resets the HEAD to the latest commit."""
        try:
            self.clean()
            self.reset_to_head()
        except GitError as e:
            raise GitError(
                self, message=f"Failed to clean and reset the repository: {e}"
            )

    def clone(
        self, no_checkout: bool = False, bare: Optional[bool] = False, **kwargs
    ) -> None:
        self._log_info("cloning repository")

        self.path.mkdir(exist_ok=True, parents=True)
        if len(os.listdir(self.path)) != 0:
            raise GitError(
                repo=self,
                message=f"destination path {self.path} is not an empty directory.",
            )

        if self.urls is None:
            raise GitError(
                repo=self, message="cannot clone repository. No urls were specified"
            )
        params = []
        if bare:
            params.append("--bare")
        elif no_checkout:
            params.append("--no-checkout")

        for name, value in kwargs.items():
            if isinstance(value, bool):
                params.append(f"--{name}")
            else:
                params.append(f"--{name} {value}")

        joined_params = " ".join(params)

        cloned = False
        for url in self.urls:
            self._log_info(f"trying to clone from {url}")
            try:
                self._git(
                    "clone {} . {}",
                    url,
                    joined_params,
                    log_success_msg=f"successfully cloned from {url}",
                    reraise_error=True,
                    timeout=60,
                    error_if_not_exists=False,
                )
            except GitError as e:
                self._log_debug(f"could not clone from {url} due to {e}")
            else:
                self._log_info(f"successfully cloned from {url}")
                cloned = True
                break

        if not cloned:
            self.raise_git_access_error(CloneRepoException)

        if self.default_branch is None:
            self.default_branch = self._determine_default_branch()

    def clone_from_disk(
        self,
        local_path: Path,
        remote_url: Optional[str] = None,
        is_bare: bool = False,
        keep_remote=False,
        branches=None,
    ) -> None:
        self.path.mkdir(parents=True, exist_ok=True)
        pygit2.clone_repository(local_path, self.path, bare=is_bare)
        if not self.is_git_repository:
            raise GitError(
                self, message=f"Could not clone repository from local path {local_path}"
            )
        repo = self.pygit_repo

        if not keep_remote:
            self.remove_remote("origin")
            if remote_url is not None:
                self.add_remote("origin", remote_url)
                self.fetch()
                if repo is not None and branches:
                    local_branch_names = [
                        branch.split("/")[-1] for branch in repo.branches.local
                    ]
                    for branch in branches:
                        if branch in local_branch_names:
                            self.set_upstream(str(branch))

    # TODO test this
    def clone_or_pull(
        self,
        branches: Optional[List[str]] = None,
        only_fetch: Optional[bool] = False,
        **kwargs,
    ) -> Tuple[Commitish | None, Commitish | None]:
        """
        Clone or fetch the specified branch for the given repo.
        Return old and new HEAD.
        """
        try:
            old_head = self.head_commit()
        except GitError:
            # repo does not exist
            old_head = None

        if old_head is None:
            self._log_debug(f"cloning {self.name}")
            self._log_debug(f"old head sha is {old_head}")
            self.clone(**kwargs)
        else:
            if branches is None:
                default_branch = self.default_branch
                if default_branch is None:
                    raise FetchException(
                        "Cannot pull/clone repository. Branch not specified and default branch could not be determined"
                    )
                branches = [default_branch]
            self._log_debug(f"pulling branches {', '.join(branches)}")
            try:
                for branch in branches:
                    if only_fetch:
                        self._git("fetch", "origin", f"{branch}:{branch}")
                    else:
                        self._git("pull", "origin", branch)
                    self._log_info(f"successfully fetched branch {branch}")
            except GitError as e:
                if "fatal" in str(e):
                    raise FetchException(f"{self.path}: {str(e)}")
                pass

        new_head = self.head_commit()

        return old_head, new_head

    def create_and_checkout_branch(
        self, branch_name: str, raise_error_if_exists: Optional[bool] = True
    ) -> None:
        repo = self.pygit_repo

        try:
            branch = repo.lookup_branch(branch_name)
            if branch is not None and raise_error_if_exists:
                raise GitError(self, message=f"Branch {branch_name} already exists")
            try:
                commit = repo.revparse_single("HEAD")
                repo.branches.local.create(branch_name, commit)
                branch = repo.lookup_branch(branch_name)
                ref = repo.lookup_reference(branch.name)
                repo.checkout(ref)
            except KeyError:
                # this will be execute if there is no HEAD pointer
                flag = "-b" if raise_error_if_exists else "-B"
                self._git(
                    "checkout {} {}",
                    flag,
                    branch_name,
                    log_success_msg=f"created and checked out branch {branch_name}",
                    log_error=True,
                    reraise_error=True,
                )

        except Exception as e:
            self._log_error(str(e))
            raise
        finally:
            self._log_info(f"Created a new branch {branch_name}")

    def create_branch(
        self, branch_name: str, commit: Optional[Commitish] = None
    ) -> None:
        repo = self.pygit_repo

        try:
            if commit is not None:
                pygit_commit = repo[commit.hash]
            else:
                pygit_commit = repo.revparse_single("HEAD")
            repo.branches.local.create(branch_name, pygit_commit)
        except Exception as e:
            self._log_error(str(e))
            raise
        finally:
            self._log_info(f"Created a new branch {branch_name}")

    def checkout_commit(self, commit: Commitish) -> None:
        self._git(
            "checkout {}",
            commit.hash,
            log_success_msg=f"checked out commit {commit.hash}",
            log_error=True,
            reraise_error=True,
        )

    def branch_unpushed_commits(self, branch_name):
        repo = self.pygit_repo

        local_branch = repo.branches.get(branch_name)
        if local_branch is None:
            # local branch does not exist
            return False, []
        try:
            upstream_full_name = local_branch.upstream_name
        except KeyError:
            # no local branch => no unpushed local commit
            return False, []
        if not upstream_full_name:
            # no upstream branch - not pushed
            return True, []
        parts = upstream_full_name.split("/")
        upstream_name = "/".join(parts[2:])

        remote_branch = repo.branches.get(upstream_name)

        # Get the last common ancestor of local and remote branches
        merge_base = repo.merge_base(local_branch.target, remote_branch.target)

        # Check for commits in local branch since the merge base that are not in the remote branch
        unpushed_commits = []
        for commit in repo.walk(local_branch.target, pygit2.GIT_SORT_TOPOLOGICAL):
            if commit.id != merge_base and not repo.descendant_of(
                remote_branch.target, commit.id
            ):
                unpushed_commits.append(commit)
            else:
                break

        return bool(unpushed_commits), [
            Commitish.from_hash(commit.id) for commit in unpushed_commits
        ]

    def commit(
        self, message: str, paths_to_commit: Optional[List[str]] = None
    ) -> Commitish:
        if not paths_to_commit:
            self._git("add -A")
        else:
            self._git(f"add {' '.join(paths_to_commit)}")
        try:
            self._git("diff --cached --exit-code --shortstat", reraise_error=True)
        except GitError:
            try:
                run("git", "-C", str(self.path), "commit", "--quiet", "-m", message)
                return Commitish.from_hash(self._git("rev-parse HEAD"))
            except subprocess.CalledProcessError as e:
                raise GitError(
                    repo=self, message=f"could not commit changes due to:\n{e}", error=e
                )
        else:
            raise NothingToCommitError(repo=self, message="No changes to commit")

    def commit_empty(self, message: str) -> Commitish:
        run(
            "git",
            "-C",
            str(self.path),
            "commit",
            "--quiet",
            "--allow-empty",
            "-m",
            message,
        )
        return Commitish.from_hash(self._git("rev-parse HEAD"))

    def commit_exists(self, commit: Commitish) -> bool:
        try:
            return bool(self._git(f"rev-parse {commit.value}"))
        except GitError:
            return False

    def commits_on_branch_and_not_other(
        self, branch1: str, branch2: str
    ) -> List[Commitish]:
        """
        Meant to find commits belonging to a branch which branches off of
        a commit from another branch. For example, to find only commits
        on a speculative branch and not on the main branch.
        """
        merge_base = self.get_merge_base(branch1, branch2)
        commits = self.all_commits_since_commit(merge_base, branch1, reverse=False)

        return commits

    def commit_before_commit(self, commit: Commitish) -> Optional[Commitish]:
        repo = self.pygit_repo

        repo_commit_id = repo.get(commit.hash).id
        for comm in repo.walk(repo_commit_id):
            hex = comm.id.hex
            if hex != commit.hash:
                return Commitish.from_hash(hex)
        return None

    def create_local_branch_from_remote_tracking(self, branch, remote="origin"):
        repo = self.pygit_repo
        remote_branch_name = f"refs/remotes/{remote}/{branch}"
        remote_branch = repo.lookup_reference(remote_branch_name)
        if remote_branch is not None:
            local_branch = repo.lookup_branch(branch, pygit2.GIT_BRANCH_LOCAL)
            if local_branch is None:
                # Create a new local branch from the remote branch
                target_commit = repo[remote_branch.target]
                repo.create_branch(branch, target_commit)

    def delete_local_branch(self, branch_name: str) -> None:
        """Deletes local branch."""
        try:
            repo = self.pygit_repo

            repo.branches.delete(branch_name)
        except KeyError:
            raise GitError(
                repo=self,
                message=f"Could not delete branch {branch_name}. Branch does not exist",
            )
        except Exception:
            raise GitError(repo=self, message=f"Could not delete branch {branch_name}.")

    def delete_remote_tracking_branch(
        self, remote_branch_name: str, force: Optional[bool] = False
    ) -> None:
        flag = "-D" if force else "-d"
        self._git(f"branch {flag} -r {remote_branch_name}", log_error=True)

    def delete_remote_branch(
        self,
        branch_name: str,
        remote: Optional[str] = None,
        no_verify: Optional[bool] = False,
    ) -> None:
        """
        Delete remote branch.
        """
        if remote is None:
            remote = self.remotes[0]
        no_verify_flag = "--no-verify" if no_verify else ""
        self._git(
            f"push {remote} --delete {branch_name} {no_verify_flag}", log_error=True
        )

    def get_commit_date(self, commit: Commitish) -> str:
        """Returns commit date of the given commit"""
        repo = self.pygit_repo

        pygit_commit = repo.get(commit.hash)
        date = datetime.datetime.utcfromtimestamp(
            pygit_commit.commit_time + pygit_commit.commit_time_offset
        )
        formatted_date = date.strftime("%Y-%m-%d")
        return formatted_date

    def get_commit_message(self, commit: Commitish) -> str:
        """Returns commit message of the given commit"""
        repo = self.pygit_repo

        pygit_commit = repo.get(commit.hash)
        return pygit_commit.message

    def get_default_branch(self, url: Optional[str] = None) -> str:
        """Get the default branch of the repository. If url is provided, return the
        default branch from the remote. Otherwise, return the default
        branch from the local repository."""
        if url is not None:
            url = url.strip()
            return self._get_default_branch_from_remote(url)
        return self._get_default_branch_from_local()

    def get_json(
        self, commit: Commitish, path: str, raw: Optional[bool] = False
    ) -> Optional[Dict]:
        s = self.get_file(commit, path, raw=raw)
        if s and isinstance(s, str):
            return json.loads(s)
        return None

    def get_file(
        self,
        commit: Commitish,
        path: str,
        raw: Optional[bool] = False,
        with_id: Optional[bool] = False,
    ) -> Tuple[str, str] | str:
        path = Path(path).as_posix()
        try:
            git_id, content = self.pygit.get_file(commit, path, raw)
            if with_id:
                return git_id, content
            return content
        except TAFError as e:
            raise e
        except Exception:
            return self._git("show {}:{}", commit, path, raw=raw)

    def get_first_commit_on_branch(
        self, branch: Optional[str] = None
    ) -> Optional[Commitish]:
        branch = branch or self.default_branch
        first_commit = self._git(
            f"rev-list --max-parents=0 {branch}", error_if_not_exists=False
        )
        return Commitish.from_hash(first_commit.strip()) if first_commit else None

    def get_last_branch_by_committer_date(self) -> Optional[str]:
        """Find the latest branch based on committer date. Should only be used for
        testing purposes"""
        branches = self._git("branch --sort=committerdate").strip().split("\n")
        if not len(branches):
            return None
        return branches[-1]

    def get_remote_url(self) -> Optional[str]:
        try:
            return self._git("config --get remote.origin.url").strip()
        except GitError:
            return None

    def delete_branch(self, branch_name: str) -> None:
        self._git("branch -D {}", branch_name, log_error=True)

    def diff_between_revisions(
        self, revision1: Optional[str] = EMPTY_TREE, revision2: Optional[str] = "HEAD"
    ) -> str:
        return self._git("diff --name-status {} {}", revision1, revision2)

    def has_remote(self) -> bool:
        return len(self.remotes) > 0

    def head_commit(self) -> Optional[Commitish]:
        """Finds sha of the commit to which the current HEAD points"""
        repo = self.pygit_repo

        try:
            return Commitish.from_hash(repo.revparse_single("HEAD").id.hex)
        except Exception:
            return None

    def fetch(
        self,
        fetch_all: Optional[bool] = False,
        branch: Optional[str] = None,
        remote: Optional[str] = "origin",
    ) -> None:
        try:
            if fetch_all:
                self._git("fetch --all", log_error=True, reraise_error=True)
            else:
                if branch is None:
                    branch = ""
                self._git(
                    "fetch {} {}", remote, branch, log_error=True, reraise_error=True
                )
        except GitError:
            self.raise_git_access_error(operation="fetch")

    def fetch_from_disk(self, local_repo_path, branches):

        repo = self.pygit_repo
        temp_remote_name = f"temp_{uuid.uuid4().hex[:8]}"
        repo.remotes.create(temp_remote_name, local_repo_path)
        remote = repo.remotes[temp_remote_name]
        remote.fetch()

        for branch in branches:
            self.create_local_branch_from_remote_tracking(branch, temp_remote_name)

        repo.remotes.delete(temp_remote_name)

    def find_first_branch_matching_pattern(
        self,
        traverse_branch_name: str,
        pattern_func: Callable[[str], bool],
        include_remotes: bool = False,
        sort_key_func: Optional[Callable[[str], bool]] = None,
    ) -> Optional[str]:
        """
        Fetches changes from a local repository on disk.
        Temporarily adds it as a remote to the current repository
        and removes that remote after the operation is completed.
        """

        branch_tips = {}
        repo: pygit2.Repository = self.pygit_repo

        # Obtain the branch reference
        branch_ref = repo.lookup_branch(traverse_branch_name)
        # Ensure the branch exists
        if branch_ref is not None:
            # Get the target commit of the branch
            branch_target = branch_ref.target
        else:
            raise GitError(
                self, message=f"Branch {traverse_branch_name} does not exist"
            )

        branches = self.branches(all=include_remotes)
        all_branch_names = []

        for branch_name in branches:
            stripped_name = self._remove_remote_prefix(branch_name)
            if stripped_name in all_branch_names:
                continue
            if pattern_func(stripped_name):
                branch = repo.lookup_branch(branch_name)
                try:
                    branch_tips[stripped_name] = branch.peel().hex
                except Exception:
                    ref = repo.references[f"refs/remotes/{branch_name}"]
                    commit = ref.peel(pygit2.Commit)
                    branch_tips[stripped_name] = commit.hex
            all_branch_names.append(stripped_name)

        if sort_key_func is not None:
            all_branch_names = sorted(all_branch_names, key=sort_key_func, reverse=True)
        # Iterate over commits from newest to oldest
        if len(branch_tips):
            for commit in repo.walk(branch_target):
                for branch_name in all_branch_names:
                    tip_hex = branch_tips.get(branch_name)
                    if tip_hex is not None and (
                        commit.hex == tip_hex or repo.descendant_of(tip_hex, commit.hex)
                    ):
                        return branch_name
        return None

    def get_current_branch(self, full_name: Optional[bool] = False) -> str:
        """Return current branch."""
        repo = self.pygit_repo

        branch = repo.lookup_reference("HEAD").resolve()
        if full_name:
            return branch.name
        return branch.shorthand

    def get_last_remote_commit(
        self, url: Optional[str] = None, branch: Optional[str] = None
    ) -> Optional[Commitish]:
        """
        Fetch the last remote commit of the specified branch
        """
        branch = branch or self.default_branch
        if url is None:
            url = self.get_remote_url()
        if url is None:
            raise FetchException(
                "Could not fetch the last remote commit. URL not found"
            )
        last_commit = self._git(f"--no-pager ls-remote {url} {branch}", log_error=True)
        if last_commit:
            last_commit = last_commit.split("\t", 1)[0]
            # in some cases (e.g. upstream is defined the result might contain a warning line)
            return Commitish.from_hash(last_commit.split()[-1])
        return None

    def get_merge_base(self, branch1: str, branch2: str) -> Optional[Commitish]:
        """Finds the best common ancestor between two branches"""
        repo = self.pygit_repo

        commit1 = self.top_commit_of_branch(branch1)
        commit2 = self.top_commit_of_branch(branch2)
        if commit1 is None or commit2 is None:
            return None
        return Commitish.from_hash(repo.merge_base(commit1.hash, commit2.hash).hex)

    def get_tracking_branch(
        self, branch: Optional[str] = "", strip_remote: Optional[bool] = False
    ) -> Optional[str]:
        """Returns tracking branch name in format origin/branch-name or None if branch does not
        track remote branch.
        """
        try:
            tracking_branch = self._git(f"rev-parse --abbrev-ref {branch}@{{u}}")
            if strip_remote:
                tracking_branch = self.branch_local_name(tracking_branch)
            return tracking_branch
        except GitError:
            return None

    def set_tracking_branch(
        self,
        branch: str,
        remote: Optional[str] = "origin",
        strip_remote: Optional[bool] = False,
    ) -> Optional[str]:
        """
        Set the tracking branch for the specified branch.
        If the branch does not exist, it will be created.
        If the remote is not specified, it will default to 'origin'.
        """
        if not self.branch_exists(branch):
            self.create_branch(branch)
        tracking_branch = f"{remote}/{branch}"
        try:
            self._git(f"branch --set-upstream-to={tracking_branch} {branch}")
            if strip_remote:
                tracking_branch = branch
            return tracking_branch
        except GitError as e:
            self._log_error(f"Failed to set tracking branch: {e}")
        return None

    def init_repo(self, bare: Optional[bool] = False) -> None:
        if self.path.is_dir():
            self.path.mkdir(exist_ok=True, parents=True)
        flag = "--bare" if bare else ""
        self._git(f"init {flag}", error_if_not_exists=False)
        if self.urls is not None and len(self.urls):
            self._git("remote add origin {}", self.urls[0])

    def is_remote_branch(self, branch_name: str) -> bool:
        """
        Checks if the name of the specified branch is a valid remote branch name
        Does not check if the branch exists
        """
        for remote in self.remotes:
            if branch_name.startswith(remote + "/"):
                return True
        return False

    def list_files_at_revision(self, commit: Commitish, path: str = "") -> List[str]:
        posix_path = Path(path).as_posix()
        try:
            return self.pygit.list_files_at_revision(commit, posix_path)
        except TAFError as e:
            raise e
        except Exception:
            self._log_warning(
                "Perfomance regression: Could not list files with pygit2. Reverting to git subprocess"
            )
            return self._list_files_at_revision(commit, posix_path)

    def _list_files_at_revision(self, commit: Commitish, path: str) -> List[str]:
        if path is None:
            path = ""
        file_names = self._git("ls-tree -r --name-only {}", commit)
        list_of_files: List = []
        if not file_names:
            return list_of_files
        for file_in_repo in file_names.split("\n"):
            if not file_in_repo.startswith(path):
                continue
            file_in_repo = os.path.relpath(file_in_repo, path)
            list_of_files.append(file_in_repo)
        return list_of_files

    def list_changed_files_at_revision(self, commit: Commitish) -> List[str]:
        repo = self.pygit_repo

        commit1 = repo.get(commit.hash)
        commit_before_commit = self.commit_before_commit(commit)
        if commit_before_commit is not None:
            commit2 = repo.get(commit_before_commit.hash)

        diff = repo.diff(commit1, commit2)

        file_names = set()
        for patch in diff:
            delta = patch.delta
            file_names.add(delta.new_file.path)
            file_names.add(delta.old_file.path)
        return list(file_names)

    def list_commits(self, branch: Optional[str] = "") -> List[Commitish]:

        return [
            Commitish.from_hash(commit.hex)
            for commit in self.list_pygit_commits(branch)
        ]

    def list_pygit_commits(self, branch: Optional[str] = "") -> List[pygit2.Commit]:
        repo = self.pygit_repo

        if branch:
            branch_obj = repo.branches.get(branch)
            latest_commit_id = branch_obj.target
        else:
            latest_commit_id = repo[repo.head.target].id

        return [commit for commit in repo.walk(latest_commit_id, pygit2.GIT_SORT_NONE)]

    def list_n_commits(
        self,
        number: Optional[int] = 10,
        start_commit: Optional[Commitish] = None,
        branch: Optional[str] = None,
    ) -> List[Commitish]:
        """List the specified number of top commits of the current branch
        Optionally skip a number of commits from the top"""
        if number is None or number <= 0:
            return []
        repo = self.pygit_repo

        if start_commit is not None:
            start_commit_id = repo.get(start_commit.hash).id
        elif branch:
            branch_obj = repo.branches.get(branch)
            start_commit_id = branch_obj.target
        else:
            start_commit_id = repo[repo.head.target].id
        commits = itertools.islice(repo.walk(start_commit_id), number + 1)
        return [
            Commitish.from_hash(commit.hex)
            for commit in commits
            if commit.hex != start_commit_id
        ]

    def list_modified_files(
        self, path: Optional[str] = None, with_status: Optional[bool] = False
    ) -> List[Tuple]:
        # TODO
        # repo.diff("HEAD")
        # go over the returned diff object
        diff_command = "diff --name-status"
        if path is not None:
            diff_command = f"{diff_command} {path}"
        modified_files = self._git(diff_command).split("\n")
        files = []
        for modified_file in modified_files:
            # ignore warning lines
            if len(modified_file) and modified_file[0] in ["A", "M", "D"]:
                if with_status:
                    files.append(tuple(modified_file.split(maxsplit=1)))
                else:
                    files.append(modified_file.split(maxsplit=1)[1])
        return files

    def list_tags(self) -> List[str]:
        return self._git("tag -l").splitlines()

    def list_untracked_files(self, path: Optional[str] = None) -> List[str]:
        ls_command = "ls-files --others"
        if path is not None:
            ls_command = f"{ls_command} {path}"
        untracked_files = self._git(ls_command).split("\n")
        return [
            untracked_file for untracked_file in untracked_files if len(untracked_file)
        ]

    def merge_commit(
        self,
        commit: Commitish,
        target_branch: Optional[str] = None,
        fast_forward_only: Optional[bool] = False,
        check_if_merge_completed: Optional[bool] = False,
    ) -> bool:
        # Determine the branch to merge into, defaulting to the current branch if not provided
        branch = target_branch or self.get_current_branch()

        fast_forward_only_flag = "--ff-only" if fast_forward_only else ""

        self._git(f"merge {commit} {fast_forward_only_flag}", log_error=True)

        self.reset_to_commit(commit, branch, hard=True)
        if check_if_merge_completed:
            try:
                self._git("rev-parse -q --verify MERGE_HEAD")
                return False
            except GitError:
                pass
        return True

    def merge_branch(
        self, branch_name: str, allow_new_commit: Optional[bool] = False
    ) -> None:
        if allow_new_commit:
            repo = self.pygit_repo

            branch = repo.lookup_branch(branch_name)
            oid = branch.target

            for commit in repo.walk(oid):
                message = commit.message
                break

            repo.merge(oid)
            self.commit(message)
            repo.state_cleanup()
        else:
            self._git("merge {}", branch_name, log_error=True)

    def pull(self):
        """Pull current branch"""
        try:
            self._git("pull", log_error=True, reraise_error=True)
        except GitError:
            self.raise_git_access_error(operation="pull")

    def push(
        self,
        branch: Optional[str] = None,
        set_upstream: Optional[bool] = False,
        force: Optional[bool] = False,
        no_verify: Optional[bool] = False,
    ) -> bool:

        if not self.has_remote():
            self._log_warning("Could not push changes. No remotes configured")
            return False

        try:
            """Push all changes"""
            if branch is None:
                branch = self.get_current_branch()

            hook_path = Path(self.path) / ".git" / "hooks" / "pre-push"
            if hook_path.exists():
                self._log_notice("Validating and pushing...")

            upstream_flag = "-u" if set_upstream else ""
            force_flag = "-f" if force else ""
            no_verify_flag = "--no-verify" if no_verify else ""
            self._git(
                "push {} {} origin {} {}",
                upstream_flag,
                force_flag,
                branch,
                no_verify_flag,
                reraise_error=True,
            )
            self._log_notice("Successfully pushed to remote")
            return True
        except GitError as e:
            raise PushFailedError(self, message=f"Push operation failed: {e}")

    def raise_git_access_error(
        self, error_cls=GitAccessDeniedException, operation=None
    ):
        hosts = {extract_hostname(url) for url in self.urls}
        unknown_hosts = [host for host in hosts if not is_host_known(host)]
        if len(unknown_hosts):
            message = _no_hosts_error_format.format(hostname=",".join(unknown_hosts))
            raise error_cls(self, operation=operation, message=message)
        repo_exists = any(repository_exists(url) for url in self.urls)
        if repo_exists:
            uses_ssh = any(url.startswith("git@") for url in self.urls)
            if uses_ssh:
                raise error_cls(
                    self, operation=operation, message=_clone_or_pull_error_message
                )
            else:
                raise error_cls(
                    self,
                    operation=operation,
                    message=_clone_or_pull_error_message_no_ssh,
                )
        raise error_cls(self)

    def remove_remote(self, remote_name: str) -> None:
        try:
            self._git("remote remove {}", remote_name)
        except GitError as e:
            if "No such remote" not in str(e):
                self._git(f"remote rename {remote_name} local")
                self._log_warning(
                    f"Could not remove remote {remote_name}. It was renamed to 'local'. Remove it manually"
                )

    def remote_exists(self, remote_name):
        repo = self.pygit_repo
        for remote in repo.remotes:
            if remote.name == remote_name:
                return True
        return False

    def rename_branch(self, old_name: str, new_name: str) -> None:
        self._git("branch -m {} {}", old_name, new_name)

    def reset_num_of_commits(
        self, num_of_commits: int, hard: Optional[bool] = False
    ) -> None:
        flag = "--hard" if hard else "--soft"
        self._git(f"reset {flag} HEAD~{num_of_commits}")

    def reset_to_commit(
        self,
        commit: Commitish,
        branch: Optional[str] = None,
        hard: Optional[bool] = False,
        reset_remote_tracking=True,
    ) -> None:
        flag = "--hard" if hard else "--soft"

        if reset_remote_tracking:
            if branch is None:
                branch = self.get_current_branch()
            self.update_branch_refs(branch, commit)

        if hard:
            self._git(f"reset {flag} HEAD")

    def restore(self, file_paths: List[str]) -> None:
        if not file_paths:
            return
        file_paths = [str(Path(file_path).as_posix()) for file_path in file_paths]
        existing, non_existing = self.check_files_exist(file_paths)
        if existing:
            self._git(f"reset HEAD -- {' '.join(existing)}")
            self._git(f"checkout HEAD -- {' '.join(existing)}")
        for path in non_existing:
            file_path = Path(path)
            if file_path.is_file():
                file_path.unlink()
            elif file_path.is_dir():
                shutil.rmtree(file_path)

    def update_branch_refs(self, branch: str, commit: Commitish) -> None:
        # Update the local branch reference to the specific commit
        self._git(f"update-ref refs/heads/{branch} {commit}")
        # Update the remote-tracking branch
        self._git(f"update-ref refs/remotes/origin/{branch} {commit}", log_error=True)

    def update_ref_for_bare_repository(self, branch: str, commit: Commitish) -> None:
        """
        Update the reference of the branch to the given commit SHA in a bare repository.
        """
        try:
            self._git(f"update-ref refs/heads/{branch} {commit}")
        except GitError:
            raise UpdateFailedError(
                f"Could not update branch {branch} to commit {commit} in bare repository {self.name}."
            )

    def reset_remote_tracking_branch(self, branch_name) -> None:
        """
        Set top commit of origing/branch to the top comit of the local branch
        Used while testing the updater
        """
        commit = self.top_commit_of_branch(branch_name)
        self._git(f"update-ref refs/remotes/origin/{branch_name} {commit}")

    def reset_to_head(self) -> None:
        self._git("reset --hard HEAD")

    def safely_get_json(self, commit: Commitish, path: str) -> Optional[Dict]:
        try:
            return self.get_json(commit, path)
        except GitError:
            self._log_debug(f"{path} not available at revision {commit}")
        except json.decoder.JSONDecodeError:
            self._log_debug(f"{path} not a valid json at revision {commit}")
        return None

    def set_remote_url(self, new_url: str, remote: Optional[str] = "origin") -> None:
        self._git(f"remote set-url {remote} {new_url}")

    def set_upstream(self, branch_name: str) -> None:
        repo = self.pygit_repo
        try:
            repo.resolve_refish(f"origin/{branch_name}")
        except KeyError:
            return

        self._git("branch -u origin/{}", branch_name)

    def something_to_commit(self) -> bool:
        """Checks if there are any uncommitted changes"""
        if self.is_bare_repository:
            # For bare repositories, use `git diff` to check for uncommitted changes
            uncommitted_changes = self._git("diff --name-only --cached")
        else:
            # For non-bare repositories, use `git status`
            uncommitted_changes = self._git("status --porcelain")
        return bool(uncommitted_changes)

    def synced_with_remote(
        self,
        branch: Optional[str] = None,
        url: Optional[str] = None,
        add_tracking_branch: Optional[bool] = False,
    ) -> bool:
        """Checks if local branch is synced with its remote branch"""
        # check if the latest local commit matches
        # the latest remote commit on the specified branch
        if not self.has_remote():
            raise NoRemoteError(self)
        if url:
            urls = [url]
        elif self.urls:
            urls = self.urls
        else:
            remote_url = self.get_remote_url()
            if remote_url is None:
                raise GitError(
                    self,
                    message="URL not specified and could not be automatically determined. Cannot check if synced",
                )
            urls = [remote_url]

        branch_name = branch or self.default_branch
        if branch_name is None:
            raise GitError(
                self,
                message="Branch not specified and default branch could not be determined",
            )

        tracking_branch = self.get_tracking_branch(branch_name, strip_remote=True)
        if not tracking_branch and not add_tracking_branch:
            return False
        else:
            tracking_branch = self.set_tracking_branch(branch_name, strip_remote=True)
        try:
            local_commit = self.top_commit_of_branch(branch_name)
        except GitError as e:
            if "unknown revision or path not in the working tree" not in str(e):
                raise e
            local_commit = None

        for url in urls:
            remote_commit = self.get_last_remote_commit(url, tracking_branch)
            if remote_commit is not None:
                break

        return local_commit == remote_commit

    def top_commit_of_branch(self, branch_name: str) -> Optional[Commitish]:
        repo = self.pygit_repo

        branch = repo.branches.get(branch_name)
        if branch is not None:
            return Commitish.from_hash(branch.target.hex)
        # a reference like HEAD
        try:
            return Commitish.from_hash(repo.revparse_single(branch_name).id.hex)
        except Exception:
            return None

    def update_local_branch(self, branch, remote_name="origin"):
        """
        Updates ref of a local branch of a bare repository where merging is not possible
        """
        repo = self.pygit_repo

        remote_branch_ref = f"refs/remotes/{remote_name}/{branch}"
        remote_branch_commit = repo.lookup_reference(remote_branch_ref).target

        # Update the local branch to point to the latest commit from the remote branch
        local_branch_ref = f"refs/heads/{branch}"
        repo.references.create(local_branch_ref, remote_branch_commit, force=True)

    def _determine_default_branch(self) -> Optional[str]:
        """Determine the default branch of the repository"""
        # try to get the default branch from the local repository
        errors = []
        try:
            return self.get_default_branch()
        except GitError as e:
            errors.append(e)
            pass

        # if the local repository does not exist or doesn't have a default branch, try to get the default branch from remote
        if self.urls:
            for url in self.urls:
                try:
                    return self.get_default_branch(url)
                except GitError as e:
                    errors.append(e)
                    pass

        self._log_debug(
            f"Cannot determine default branch with git -C at {self.path}: {errors}"
        )
        return None

    def top_commit_of_remote_branch(
        self, branch, remote="origin"
    ) -> Optional[Commitish]:
        """
        Fetches the top commit of the specified remote tracking branch.

        """
        remote_branch = f"{remote}/{branch}"
        if not self.branch_exists(remote_branch, include_remotes=True):
            raise GitError(
                self, message=f"Remote branch {remote_branch} does not exist"
            )
        return self.top_commit_of_branch(remote_branch)

    def _remove_remote_prefix(self, branch_name):
        for remote in self.remotes:
            prefix = f"{remote}/"
            if branch_name.startswith(prefix):
                return branch_name[len(prefix) :]
            return branch_name
        return branch_name

    def _validate_repo_name(self, name: str) -> str:
        """Ensure the repo name is not malicious"""
        match = _repo_name_re.match(name)
        if not match:
            taf_logger.error(f"Repository name {name} is not valid")
            raise InvalidRepositoryError(
                "Repository name must be in format namespace/repository "
                "and can only contain letters, numbers, underscores and "
                f'dashes, but got "{name}"'
            )
        return name

    def _validate_repo_path(
        self, library_dir: Path, name: Optional[str] = None, path: Optional[Path] = None
    ) -> Path:
        """
        validate repo path
        (since this is coming from potentially untrusted data)
        """
        # using OS to avoid resolve adding drive letter name on Windows
        repo_dir = os.path.join(str(library_dir), name or "")
        repo_dir = os.path.normpath(repo_dir)
        if not repo_dir.startswith(str(Path(library_dir))):
            taf_logger.error(f"Repository path/name {library_dir}/{name} is not valid")
            raise InvalidRepositoryError(
                f"Repository path/name {library_dir}/{name} is not valid"
            )
        repo_dir_path = Path(repo_dir).expanduser().resolve()
        if path is not None and path != repo_dir_path:
            raise InvalidRepositoryError(
                "Both library dir and name pair and path specified and are not equal. Omit the path."
            )
        return repo_dir_path

    def _validate_url(self, url: str) -> None:
        """ensure valid URL"""
        for _url_re in [_http_fttp_url, _ssh_url]:
            match = _url_re.match(url)
            if match:
                return
        self._log_error(f"URL ({url}) is not valid")
        raise InvalidRepositoryError(
            f'Repository URL must be a valid URL, but got "{url}".'
        )

    def _validate_urls(self, urls: Optional[List[str]]) -> Optional[List[str]]:
        def _find_url(path, url):
            try:
                if (path / url).resolve().is_dir():
                    return str((path / url).resolve())
            except OSError:
                pass
            if os.path.isabs(url):
                return url
            return str((path).resolve())

        if urls is not None:
            if settings.update_from_filesystem is False:
                for url in urls:
                    self._validate_url(url)
            else:
                # resolve paths and deduplicate
                urls = sorted((_find_url(self.path, url) for url in urls), reverse=True)
        return urls


_clone_or_pull_error_message = (
    "The remote repository exists, so this is probably due to the lack of privileges or SSH key issues. "
    "Here are some steps you can take to resolve common issues:\n\n"
    "1. Check Repository Access:\n"
    "   - If the repository is private, verify that your account has been granted access.\n\n"
    "2. Check SSH Key Configuration:\n"
    "   - Ensure your SSH key is correctly added to your Git hosting account (GitHub, GitLab, Bitbucket, etc.).\n"
    "   - Verify that your SSH key does not require a passphrase, or use an SSH agent to manage the passphrase.\n\n"
    "3. Using an SSH Agent:\n"
    "   - If your SSH key is passphrase-protected, start the ssh-agent in the background:\n"
    "       eval $(ssh-agent -s)\n"
    "   - Add your SSH key to the ssh-agent:\n"
    "       ssh-add /path/to/your/private/key\n"
    "4. If Problems Persist:\n"
    "   - If you are using Windows and encounter issues, consider running these commands in Bash or another Unix-like shell available on Windows, such as Git Bash or WSL.\n"
    "   - Try using a different SSH key that does not require a passphrase.\n"
)


_clone_or_pull_error_message_no_ssh = (
    "The remote repository exists, so this issue is probably due to lack of privileges.\n"
    "Verify that you have access to the repository if it is private, and verify your HTTPS configuration.\n"
    "Consider switching to SSH for potentially enhanced security and easier handling of credentials."
)


_no_hosts_error_format = (
    "Error: The host(s) '{hostname}' not recognized."
    "To add a host to your known_hosts file, manually connect via SSH using the command:\n"
    "ssh -T git@{hostname}\n"
    "Accept the host key to proceed.\n"
)

_remote_branch_re = re.compile(r"^(refs/heads/)")

_local_branch_re = re.compile(r"^(origin/)")

_repo_name_re = re.compile(r"^\w[\w_-]*/\w[\w_-]*$")

_http_fttp_url = re.compile(
    r"^(?:http|ftp)s?://"  # http:// or https://
    # domain...
    r"(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+(?:[A-Z]{2,6}\.?|[A-Z0-9-]{2,}\.?)|"
    r"localhost|"  # localhost...
    r"\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})"  # ...or ip
    r"(?::\d+)?"  # optional port
    r"(?:/?|[/?]\S+)$",
    re.IGNORECASE,
)

_ssh_url = re.compile(
    r"((git|ssh|http(s)?)|(git@[\w\.]+))(:(//)?)([\w\.@\:/\-~]+)(\.git)?(/)?"
)


def extract_hostname(url):
    """Extract the hostname from a Git URL, which can be either SSH or HTTP(S)."""
    if url.startswith("git@"):
        # Handle SSH URL
        match = re.match(r"git@(.*?):", url)
    else:
        # Handle HTTP(S) URL
        match = re.match(r"https?://([^/]+)/", url)

    if match:
        return match.group(1)
    else:
        return None


def is_host_known(hostname):
    """Check if the given hostname is in the known_hosts file."""
    known_hosts_path = os.path.expanduser("~/.ssh/known_hosts")
    try:
        with open(known_hosts_path, "r") as file:
            for line in file:
                if line.startswith(hostname) or hostname in line.split():
                    return True
        return False
    except FileNotFoundError:
        print("Known hosts file not found.")
        return False
    except Exception as e:
        print(f"An error occurred: {str(e)}")
        return False


def repository_exists(url):
    """Check if the repository URL exists by making a HEAD request to the URL."""
    # Convert SSH URL to HTTP URL
    if url.startswith("git@"):
        # General pattern: git@HOST:USER/REPO
        http_url = re.sub(r"git@(.*?):(.*?)/(.*)\.git", r"https://\1/\2/\3", url)
    elif url.startswith("git://"):
        http_url = url.replace("git://", "https://").replace(".git", "")
    else:
        http_url = url

    try:
        response = requests.head(http_url)  # nosec B113
        return response.status_code == 200
    except requests.RequestException as e:
        print(f"Error checking repository URL: {e}")
        return False
