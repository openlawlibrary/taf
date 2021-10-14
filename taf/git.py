import json
import os
import re
import shutil
import subprocess
import logging
from collections import OrderedDict
from functools import reduce
from pathlib import Path

import taf.settings as settings
from taf.exceptions import (
    CloneRepoException,
    FetchException,
    InvalidRepositoryError,
    GitError,
)
from taf.log import taf_logger
from taf.utils import run

EMPTY_TREE = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"


class GitRepository:
    def __init__(
        self,
        library_dir=None,
        name=None,
        urls=None,
        custom=None,
        default_branch="main",
        path=None,
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
          default_branch (str): repository's default branch ("main" if not defined)
        """
        if isinstance(library_dir, str):
            library_dir = Path(library_dir)
        if isinstance(path, str):
            path = Path(path)

        if (library_dir, name).count(None) == 1:
            raise InvalidRepositoryError(
                "Both library_dir and name need to be specified"
            )

        if name is not None:
            self.name = self._validate_repo_name(name)
            self.path = self._validate_repo_path(library_dir, name, path)
            self.library_dir = library_dir.resolve()
        elif path is None:
            raise InvalidRepositoryError(
                "Either speicfy library dir and name pair or path!"
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
            self.path = self._validate_repo_path(path, None)

        self.urls = self._validate_urls(urls)
        self.default_branch = default_branch
        self.custom = custom or {}

    @classmethod
    def from_json_dict(cls, json_data):
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
        logging.WARNING: taf_logger.warning,
        logging.ERROR: taf_logger.error,
        logging.CRITICAL: taf_logger.critical,
    }

    log_template = "{}{}"

    _remotes = None

    @property
    def remotes(self):
        if self._remotes is None:
            self._remotes = self._git("remote").split("\n")
        return self._remotes

    @property
    def is_git_repository_root(self):
        """Check if path is git repository."""
        git_path = self.path / ".git"
        return self.is_git_repository and (git_path.is_dir() or git_path.is_file())

    @property
    def is_git_repository(self):
        try:
            self._git("rev-parse --git-dir")
            return True
        except GitError:
            return False

    @property
    def initial_commit(self):
        return (
            self._git(
                "rev-list --max-parents=0 HEAD", error_if_not_exists=False
            ).strip()
            if self.is_git_repository
            else None
        )

    @property
    def log_prefix(self):
        return f"Repo {self.name}: "

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

    def _log(self, log_func, message):
        log_func(self.log_template, self.log_prefix, message)

    def _log_debug(self, message):
        self._log(self.logging_functions[logging.DEBUG], message)

    def _log_info(self, message):
        self._log(self.logging_functions[logging.INFO], message)

    def _log_warning(self, message):
        self._log(self.logging_functions[logging.WARNING], message)

    def _log_error(self, message):
        self._log(self.logging_functions[logging.ERROR], message)

    def _log_critical(self, message):
        self._log(self.logging_functions[logging.CRITICAL], message)

    def all_commits_on_branch(self, branch=None, reverse=True):
        """Returns a list of all commits on the specified branch. If branch is None,
        all commits on the currently checked out branch will be returned
        """
        if branch is None:
            branch = ""
        commits = self._git("log {} --format=format:%H", branch, log_error=True)
        if commits is not None:
            commits = commits.strip()
        if not commits:
            commits = []
        else:
            commits = commits.split("\n")
            if reverse:
                commits.reverse()

        self._log_debug(f"found the following commits: {', '.join(commits)}")
        return commits

    def all_commits_since_commit(self, since_commit, branch=None, reverse=True):
        """Returns a list of all commits since the specified commit on the
        specified or currently checked out branch
        """
        if since_commit is None:
            return self.all_commits_on_branch(branch=branch, reverse=reverse)
        if branch is None:
            branch = "HEAD"
        commits = self._git("rev-list {}..{}", since_commit, branch, log_error=True)
        if commits is not None:
            commits = commits.strip()
        if not commits:
            commits = []
        else:
            commits = commits.split("\n")
            if reverse:
                commits.reverse()

        self._log_debug(
            f"found the following commits after commit {since_commit}: {', '.join(commits)}"
        )
        return commits

    def all_fetched_commits(self, branch=None):
        branch = branch or self.default_branch
        commits = self._git("rev-list ..origin/{}", branch).strip()
        if not commits:
            commits = []
        else:
            commits = commits.split("\n")
            commits.reverse()
        self._log_debug(f"fetched the following commits {', '.join(commits)}")
        return commits

    def branches(self, remote=False, all=False, strip_remote=False):
        """Returns all branches."""
        flag = "-r" if remote else "-a" if all else ""
        error_msg = "remote" if remote else "all" if all else ""
        branches = [
            branch.strip('"').strip("'").strip()
            for branch in self._git(
                "branch {} --format='%(refname:short)'",
                flag,
                log_error_msg=f"Repo {self.name}: could not list {error_msg} branches",
                reraise_error=True,
            ).split("\n")
        ]

        if strip_remote:
            remotes = self.remotes
            branches = set(
                [
                    reduce(lambda b, r: b.replace(f"{r}/", ""), remotes, branch)
                    for branch in branches
                ]
            )

        return branches

    def branches_containing_commit(self, commit, strip_remote=False, sort_key=None):
        """Finds all branches that contain the given commit"""
        local_branches = self._git(f"branch --contains {commit}", log_error=True).split(
            "\n"
        )
        if local_branches:
            local_branches = [
                branch.replace("*", "").replace("+", "").strip()
                for branch in local_branches
            ]
        remote_branches = self._git(
            f"branch -r --contains {commit}", log_error=True
        ).split("\n")
        filtered_remote_branches = []
        if remote_branches:
            for branch in remote_branches:
                branch = branch.strip()
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

    def branch_exists(self, branch_name, include_remotes=True):
        """
        Checks if a branch with the given name exists.
        If include_remotes is set to True, this checks if
        a remote branch exists.
        """
        branch = self._git(
            f"branch --list {branch_name}", log_error=True, reraise_error=True
        )
        # this git command should return the branch's name if it exists
        # empty string otherwise
        if branch:
            return True
        if include_remotes:
            for remote in self.remotes:
                remote_branch = self._git(
                    f"branch -r --list {remote}/{branch_name}",
                    log_error_msg=f"Repo {self.name}: could not list remote branches",
                    reraise_error=True,
                )
                # this command should return the branch's name if the remote tracking branch
                # exists
                # it will also return some warnings if there are problems with some refs
                if branch_name in remote_branch:
                    return True

                # finally, check remote branch
                if self.has_remote():
                    return branch_name in self._git(
                        f"ls-remote --heads origin {branch_name}",
                        log_error_msg=f"Repo {self.name}: could check if the branch exists in the remote repository",
                        reraise_error=True,
                    )

        return False

    def branch_off_commit(self, branch_name, commit):
        """Create a new branch by branching off of the specified commit"""
        self._git(
            f"checkout -b {branch_name} {commit}",
            log_error=True,
            reraise_error=True,
            log_success_msg=f"Repo {self.name}: created a new branch {branch_name} from branching off of {commit}",
        )

    def branch_local_name(self, remote_branch_name):
        """Strip remote from the given remote branch"""
        for remote in self.remotes:
            if remote_branch_name.startswith(remote + "/"):
                return remote_branch_name.split("/", 1)[1]

    def checkout_branch(self, branch_name, create=False, raise_anyway=False):
        """Check out the specified branch. If it does not exists and
        the create parameter is set to True, create a new branch.
        If the branch does not exist and create is set to False,
        raise an exception."""
        try:
            self._git(
                "checkout {}",
                branch_name,
                log_success_msg=f"Repo {self.name}: checked out branch {branch_name}",
            )
        except GitError as e:
            if raise_anyway:
                raise (e)

            # skip worktree errors
            if "is already checked out at" in str(e):
                return

            if create:
                self.create_and_checkout_branch(branch_name)
            else:
                self._log_error(f"could not checkout branch {branch_name}")
                raise (e)

    def checkout_paths(self, commit, *args):
        for file_path in args:
            self._git(
                f"checkout {commit} {file_path}", log_error=True, reraise_error=True
            )

    def checkout_orphan_branch(self, branch_name):
        """Creates orphan branch"""
        self._git(
            f"checkout --orphan {branch_name}", log_error=True, reraise_error=True
        )
        try:
            self._git("rm -rf .")
        except GitError:  # If repository is empty
            pass

    def clean(self):
        self._git("clean -fd")

    def clone(self, no_checkout=False, bare=False, **kwargs):
        self._log_info("cloning repository")
        shutil.rmtree(self.path, True)
        self.path.mkdir(exist_ok=True, parents=True)
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

        params = " ".join(params)

        cloned = False
        for url in self.urls:
            self._log_info(f"trying to clone from {url}")
            try:
                self._git(
                    "clone {} . {}",
                    url,
                    params,
                    log_success_msg=f"successfully cloned from {url}",
                    log_error_msg=f"cannot clone from url {url}",
                    reraise_error=True,
                )
            except GitError as e:
                self._log_info(f"could not clone from {url} due to {e}")
            else:
                self._log_info(f"successfully cloned from {url}")
                cloned = True
                break

        if not cloned:
            raise CloneRepoException(self)

    def clone_or_pull(self, branches=None, only_fetch=False, **kwargs):
        """
        Clone or fetch the specified branch for the given repo.
        Return old and new HEAD.
        """
        if branches is None:
            branches = [self.default_branch]
        self._log_debug(f"cloning or pulling branches {', '.join(branches)}")

        old_head = self.head_commit_sha()
        if old_head is None:
            self._log_debug(f"old head sha is {old_head}")
            self.clone(**kwargs)
        else:
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

        new_head = self.head_commit_sha()

        return old_head, new_head

    def create_and_checkout_branch(self, branch_name, raise_error_if_exists=True):
        flag = "-b" if raise_error_if_exists else "-B"
        self._git(
            "checkout {} {}",
            flag,
            branch_name,
            log_success_msg=f"created and checked out branch {branch_name}",
            log_error=True,
            reraise_error=True,
        )

    def create_branch(self, branch_name, commit=None):
        if commit is None:
            commit = ""
        self._git(
            "branch {} {}",
            branch_name,
            commit,
            log_success_msg=f"created branch {branch_name}",
            log_error=True,
            reraise_error=True,
        )

    def create_local_branch(self, branch_name):
        """Create local branch by checking it out if it does not exist and making sure
        to check out previously checked out branch
        """
        if not self.branch_exists(branch_name, include_remotes=False):
            current_branch = self.get_current_branch()
            self.checkout_branch(branch_name)
            self.checkout_branch(current_branch)

    def checkout_commit(self, commit):
        self._git(
            "checkout {}",
            commit,
            log_success_msg=f"checked out commit {commit}",
            log_error=True,
            reraise_error=True,
        )

    def commit(self, message):
        """Create a commit with the provided message on the currently checked out branch"""
        self._git("add -A")
        try:
            self._git("diff --cached --exit-code --shortstat", reraise_error=True)
        except GitError:
            try:
                run("git", "-C", str(self.path), "commit", "--quiet", "-m", message)
            except subprocess.CalledProcessError as e:
                raise GitError(
                    repo=self, message=f"could not commit changes due to:\n{e}"
                )
        return self._git("rev-parse HEAD")

    def commit_empty(self, message):
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
        return self._git("rev-parse HEAD")

    def commits_on_branch_and_not_other(
        self, branch1, branch2, include_branching_commit=False
    ):
        """
        Meant to find commits belonging to a branch which branches off of
        a commit from another branch. For example, to find only commits
        on a speculative branch and not on the main branch.
        """

        self._log_debug(
            f"finding commits which are on branch {branch1}, but not on branch {branch2}"
        )
        commits = self._git(
            "log {} --not {} --no-merges --format=format:%H", branch1, branch2
        )
        commits = commits.split("\n") if commits else []
        if include_branching_commit:
            branching_commit = self._git("rev-list -n 1 {}~1", commits[-1])
            commits.append(branching_commit)
        self._log_debug(f"found the following commits: {commits}")
        return commits

    def delete_local_branch(self, branch_name, force=False):
        """Deletes local branch."""
        flag = "-D" if force else "-d"
        self._git(f"branch {flag} {branch_name}", log_error=True)

    def delete_remote_tracking_branch(self, remote_branch_name, force=False):
        flag = "-D" if force else "-d"
        self._git(f"branch {flag} -r {remote_branch_name}", log_error=True)

    def delete_remote_branch(self, branch_name, remote=None):
        if remote is None:
            remote = self.remotes[0]
        self._git(f"push {remote} --delete {branch_name}", log_error=True)

    def get_commit_message(self, commit):
        """Returns commit message of the given commit"""
        return self._git("log --format=%B -n 1 {}", commit).strip()

    def get_commit_sha(self, behind_head):
        """Get commit sha of HEAD~{behind_head}"""
        return self._git("rev-parse HEAD~{}", behind_head)

    def get_json(self, commit, path, raw=False):
        s = self.get_file(commit, path, raw=raw)
        return json.loads(s)

    def get_file(self, commit, path, raw=False):
        path = Path(path).as_posix()
        return self._git("show {}:{}", commit, path, raw=raw)

    def get_first_commit_on_branch(self, branch=None):
        branch = branch or self.default_branch
        first_commit = self._git(
            f"rev-list --max-parents=0 {branch}", error_if_not_exists=False
        )
        return first_commit.strip() if first_commit else None

    def get_last_branch_by_committer_date(self):
        """Find the latest branch based on committer date. Should only be used for
        testing purposes"""
        branches = self._git("branch --sort=committerdate").strip().split("\n")
        if not len(branches):
            return None
        return branches[-1]

    def get_remote_url(self):
        try:
            return self._git("config --get remote.origin.url").strip()
        except GitError:
            return None

    def delete_branch(self, branch_name):
        self._git("branch -D {}", branch_name, log_error=True)

    def diff_between_revisions(self, revision1=EMPTY_TREE, revision2="HEAD"):
        return self._git("diff --name-status {} {}", revision1, revision2)

    def has_remote(self):
        return bool(self._git("remote"))

    def head_commit_sha(self):
        """Finds sha of the commit to which the current HEAD points"""
        try:
            return self._git("rev-parse HEAD")
        except GitError:
            return None

    def fetch(self, fetch_all=False, branch=None, remote="origin"):
        if fetch_all:
            self._git("fetch --all", log_error=True)
        else:
            if branch is None:
                branch = ""
            self._git("fetch {} {}", remote, branch, log_error=True)

    def find_worktree_path_by_branch(self, branch_name):
        """Returns path of the workree where the branch is checked out, or None if not checked out in any worktree"""
        worktrees = self.list_worktrees()
        for path, _, _branch_name in worktrees.values():
            if _branch_name == branch_name:
                return path
        return None

    def get_current_branch(self):
        """Return current branch."""
        return self._git("rev-parse --abbrev-ref HEAD").strip()

    def get_last_remote_commit(self, url, branch=None):
        """
        Fetch the last remote commit of the specified branch
        """
        branch = branch or self.default_branch
        if url is None:
            raise FetchException(
                "Could not fetch the last remote commit. URL not specified"
            )
        last_commit = self._git(f"--no-pager ls-remote {url} {branch}", log_error=True)
        if last_commit:
            last_commit = last_commit.split("\t", 1)[0]
            # in some cases (e.g. upstream is defined the result might contain a warning line)
            return last_commit.split()[-1]

    def get_merge_base(self, branch1, branch2):
        """Finds the best common ancestor between two branches"""
        return self._git(f"merge-base {branch1} {branch2}", log_error=True)

    def get_tracking_branch(self, branch="", strip_remote=False):
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

    def init_repo(self, bare=False):
        if self.path.is_dir():
            self.path.mkdir(exist_ok=True, parents=True)
        flag = "--bare" if bare else ""
        self._git(f"init {flag}", error_if_not_exists=False)
        if self.urls is not None and len(self.urls):
            self._git("remote add origin {}", self.urls[0])

    def is_remote_branch(self, branch_name):
        for remote in self.remotes:
            if branch_name.startswith(remote + "/"):
                return True
        return False

    def list_files_at_revision(self, commit, path=""):
        if path is None:
            path = ""
        file_names = self._git("ls-tree -r --name-only {}", commit)
        list_of_files = []
        if not file_names:
            return list_of_files
        for file_in_repo in file_names.split("\n"):
            if not file_in_repo.startswith(path):
                continue
            file_in_repo = os.path.relpath(file_in_repo, path)
            list_of_files.append(file_in_repo)
        return list_of_files

    def list_changed_files_at_revision(self, commit):
        file_names = self._git("diff-tree --no-commit-id --name-only -r {}", commit)
        return (file_names or []).split("\n")

    def list_commits(self, branch="", **kwargs):
        params = []
        for name, value in kwargs.items():
            params.append(f"--{name}={value}")

        return self._git("log {} {}", branch, " ".join(params)).split("\n")

    def list_commit_shas(self, branch=None):
        branch = branch or self.default_branch
        return self.list_commits(branch, format="format:%H")

    def list_n_commits(self, number=10, skip=None, branch=None):
        """List the specified number of top commits of the current branch
        Optionally skip a number of commits from the top"""
        if branch is None:
            branch = ""
        if skip:
            commits = self._git(
                f"log {branch} --format=format:%H --skip={skip} -n {number}"
            )
        else:
            commits = self._git(f"log {branch} --format=format:%H -n {number}")
        return commits.split("\n") if commits else []

    def list_modified_files(self, path=None, with_status=False):
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

    def list_untracked_files(self, path=None):
        ls_command = "ls-files --others"
        if path is not None:
            ls_command = f"{ls_command} {path}"
        untracked_files = self._git(ls_command).split("\n")
        return [
            untracked_file for untracked_file in untracked_files if len(untracked_file)
        ]

    def list_worktrees(self):
        """
        Returns a dictionary containing information about repository's worktrees:
        {
            "worktree1_path: (worktree1_path, worktree1_commit, worktree1_branch),
            "worktree2_path: (worktree2_path, worktree2_commit, worktree2_branch),
            ...
        }
        """
        worktrees_list = self._git("worktree list")
        worktrees = [w.split() for w in worktrees_list.splitlines() if w]
        return {
            Path(wt[0]): (Path(wt[0]), wt[1], wt[2].replace("[", "").replace("]", ""))
            for wt in worktrees
        }

    def merge_commit(self, commit):
        self._git("merge {}", commit, log_error=True)

    def pull(self):
        """Pull current branch"""
        self._git("pull", log_error=True)

    def push(self, branch=None, set_upstream=False, force=False):
        """Push all changes"""
        if branch is None:
            branch = self.get_current_branch()
        upstream_flag = "-u" if set_upstream else ""
        force_flag = "-f" if force else ""
        self._git(
            "push {} {} origin {}", upstream_flag, force_flag, branch, log_error=True
        )

    def rename_branch(self, old_name, new_name):
        self._git("branch -m {} {}", old_name, new_name)

    def reset_num_of_commits(self, num_of_commits, hard=False):
        flag = "--hard" if hard else "--soft"
        self._git(f"reset {flag} HEAD~{num_of_commits}")

    def reset_to_commit(self, commit, hard=False):
        flag = "--hard" if hard else "--soft"
        self._git(f"reset {flag} {commit}")

    def reset_to_head(self):
        self._git("reset --hard HEAD")

    def safely_get_json(self, commit, path):
        try:
            return self.get_json(commit, path)
        except GitError:
            self._log_debug(f"{path} not available at revision {commit}")
        except json.decoder.JSONDecodeError:
            self._log_debug(f"{path} not a valid json at revision {commit}")
        return None

    def set_remote_url(self, new_url, remote="origin"):
        self._git(f"remote set-url {remote} {new_url}")

    def set_upstream(self, branch_name):
        self._git("branch -u origin/{}", branch_name)

    def something_to_commit(self):
        """Checks if there are any uncommitted changes"""
        uncommitted_changes = self._git("status --porcelain")
        return bool(uncommitted_changes)

    def synced_with_remote(self, branch=None, url=None):
        """Checks if local branch is synced with its remote branch"""
        # check if the latest local commit matches
        # the latest remote commit on the specified branch
        branch = branch or self.default_branch
        if url is None:
            if self.urls is not None and len(self.urls):
                url = self.urls[0]
            else:
                url = self.get_remote_url()

        tracking_branch = self.get_tracking_branch(branch, strip_remote=True)
        if not tracking_branch:
            return False

        try:
            local_commit = self._git(f"rev-parse {branch}")
        except GitError as e:
            if "unknown revision or path not in the working tree" not in str(e):
                raise e
            local_commit = None

        remote_commit = self.get_last_remote_commit(url, tracking_branch)

        return local_commit == remote_commit

    def top_commit_of_branch(self, branch):
        return self._git(f"rev-parse {branch}")

    def _validate_repo_name(self, name):
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

    def _validate_repo_path(self, library_dir, name, path=None):
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
        repo_dir = Path(repo_dir).resolve()
        if path is not None and path != repo_dir:
            raise InvalidRepositoryError(
                "Both library dir and name pair and path specified and are not equal. Omit the path."
            )
        return repo_dir

    def _validate_url(self, url):
        """ensure valid URL"""
        for _url_re in [_http_fttp_url, _ssh_url]:
            match = _url_re.match(url)
            if match:
                return
        self._log_error(f"URL ({url}) is not valid")
        raise InvalidRepositoryError(
            f'Repository URL must be a valid URL, but got "{url}".'
        )

    def _validate_urls(self, urls):
        if urls is not None:
            if settings.update_from_filesystem is False:
                for url in urls:
                    self._validate_url(url)
            else:
                urls = [
                    str((self.path / url).resolve())
                    if (self.path / url).resolve().is_dir()
                    else str((self.path).resolve())
                    if not os.path.isabs(url)
                    else url
                    for url in urls
                ]
        return urls


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
