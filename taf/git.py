import json
import os
import re
import shutil
import subprocess
from collections import OrderedDict
from functools import reduce
from pathlib import Path

import taf.settings as settings
from taf.exceptions import InvalidRepositoryError, CloneRepoException, FetchException
from taf.log import taf_logger
from taf.utils import run

EMPTY_TREE = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"


class GitRepository:
    def __init__(
        self,
        path,
        repo_urls=None,
        additional_info=None,
        default_branch="master",
        repo_name=None,
        *args,
        **kwargs,
    ):
        """
    Args:
      path: repository's path
      repo_urls: repository's urls (optional)
      additional_info: a dictionary containing other data (optional)
      default_branch: repository's default branch
    """
        self._path = Path(path).resolve()
        if repo_name is None:
            repo_name = self._path.name
        self.name = repo_name
        self.default_branch = default_branch
        if repo_urls is not None:
            if settings.update_from_filesystem is False:
                for url in repo_urls:
                    _validate_url(url)
            else:
                repo_urls = [
                    os.path.normpath(os.path.join(self.path, url))
                    if not os.path.isabs(url)
                    else url
                    for url in repo_urls
                ]
        self.repo_urls = repo_urls
        self.additional_info = additional_info

    _remotes = None

    @property
    def path(self):
        return str(self._path)

    @property
    def remotes(self):
        if self._remotes is None:
            self._remotes = self._git("remote").split("\n")
        return self._remotes

    @property
    def is_git_repository_root(self):
        """Check if path is git repository."""
        git_path = self._path / ".git"
        return self.is_git_repository and (git_path.is_dir() or git_path.is_file())

    @property
    def is_git_repository(self):
        try:
            self._git("rev-parse --git-dir")
            return True
        except subprocess.CalledProcessError:
            return False

    @property
    def initial_commit(self):
        return (
            self._git("rev-list --max-parents=0 HEAD").strip()
            if self.is_git_repository
            else None
        )

    def is_remote_branch(self, branch_name):
        for remote in self.remotes:
            if branch_name.startswith(remote + "/"):
                return True
        return False

    def _git(self, cmd, *args, **kwargs):
        """Call git commands in subprocess
    e.g.:
      self._git('checkout {}', branch_name)
    """
        log_error = kwargs.pop("log_error", False)
        log_error_msg = kwargs.pop("log_error_msg", "")
        reraise_error = kwargs.pop("reraise_error", False)
        log_success_msg = kwargs.pop("log_success_msg", "")

        if len(args):
            cmd = cmd.format(*args)
        command = f"git -C {self.path} {cmd}"
        if log_error or log_error_msg:
            try:
                result = run(command)
                if log_success_msg:
                    taf_logger.debug("Repo {}:" + log_success_msg, self.name)
            except subprocess.CalledProcessError as e:
                if log_error_msg:
                    taf_logger.error(log_error_msg)
                else:
                    taf_logger.error(
                        "Repo {}: error occurred while executing {}:\n{}",
                        self.name,
                        command,
                        e.output,
                    )
                if reraise_error:
                    raise
        else:
            result = run(command)
            if log_success_msg:
                taf_logger.debug("Repo {}: " + log_success_msg, self.name)
        return result

    def all_commits_on_branch(self, branch=None, reverse=True):
        """Returns a list of all commits on the specified branch. If branch is None,
        all commits on the currently checked out branch will be returned
        """
        if branch is None:
            branch = ""
        commits = self._git("log {} --format=format:%H", branch).strip()
        if not commits:
            commits = []
        else:
            commits = commits.split("\n")
            if reverse:
                commits.reverse()

        taf_logger.debug(
            "Repo {}: found the following commits: {}", self.name, ", ".join(commits)
        )
        return commits

    def all_commits_since_commit(self, since_commit, branch=None, reverse=True):
        """Returns a list of all commits since the specified commit on the
        currently checked out branch
        """
        if since_commit is None:
            return self.all_commits_on_branch(branch=branch, reverse=reverse)
        if branch is None:
            branch = "HEAD"
        commits = self._git("rev-list {}..{}", since_commit, branch).strip()
        if not commits:
            commits = []
        else:
            commits = commits.split("\n")
            if reverse:
                commits.reverse()

        taf_logger.debug(
            "Repo {}: found the following commits after commit {}: {}",
            self.name,
            since_commit,
            ", ".join(commits),
        )
        return commits

    def all_fetched_commits(self, branch="master"):
        commits = self._git("rev-list ..origin/{}", branch).strip()
        if not commits:
            commits = []
        else:
            commits = commits.split("\n")
            commits.reverse()
        taf_logger.debug(
            "Repo {}: fetched the following commits {}", self.name, ", ".join(commits)
        )
        return commits

    def branches(self, remote=False, all=False, strip_remote=False):
        """Returns all branches."""
        flag = "-r" if remote else "-a" if all else ""
        branches = [
            branch.strip('"').strip("'").strip()
            for branch in self._git(
                "branch {} --format='%(refname:short)'", flag
            ).split("\n")
        ]

        if all and strip_remote:
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
        local_branches = self._git(f"branch --contains {commit}").split("\n")
        if local_branches:
            local_branches = [
                branch.replace("*", "").strip() for branch in local_branches
            ]
        remote_branches = self._git(f"branch -r --contains {commit}").split("\n")
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
        branch = self._git(f"branch --list {branch_name}")
        # this git command should return the branch's name if it exists
        # empty string otherwise
        if branch:
            return True
        if include_remotes:
            for remote in self.remotes:
                remote_branch = self._git(f"branch -r --list {remote}/{branch_name}")
                # this command should return the branch's name if the remote branch
                # exists
                # it will also return some warnings if there are problems with some refs
                if branch_name in remote_branch:
                    return True
        return False

    def branch_off_commit(self, branch_name, commit):
        """Create a new branch by branching off of the specified commit"""
        self._git(f"checkout -b {branch_name} {commit}")

    def branch_local_name(self, remote_branch_name):
        """Strip remote from the given remote branch"""
        for remote in self.remotes:
            if remote_branch_name.startswith(remote + "/"):
                return remote_branch_name.split("/", 1)[1]

    def checkout_branch(self, branch_name, create=False):
        """Check out the specified branch. If it does not exists and
    the create parameter is set to True, create a new branch.
    If the branch does not exist and create is set to False,
    raise an exception."""
        try:
            self._git(
                "checkout {}",
                branch_name,
                log_error=True,
                reraise_error=True,
                log_success_msg=f"checked out branch {branch_name}",
            )
        except subprocess.CalledProcessError as e:
            # skip worktree errors
            if "is already checked out at" in e.output:
                return

            if create:
                self.create_and_checkout_branch(branch_name)
            else:
                raise (e)

    def checkout_paths(self, commit, *args):
        for file_path in args:
            self._git(f"checkout {commit} {file_path}")

    def clean(self):
        self._git("clean -fd")

    def clone(self, no_checkout=False, bare=False):

        taf_logger.info("Repo {}: cloning repository", self.name)
        shutil.rmtree(self.path, True)
        self._path.mkdir(exist_ok=True, parents=True)
        if self.repo_urls is None:
            raise Exception("Cannot clone repository. No urls were specified")
        params = ""
        if bare:
            params = "--bare"
        elif no_checkout:
            params = "--no-checkout"
        for url in self.repo_urls:
            try:
                self._git(
                    "clone {} . {}", url, params, log_success_msg="successfully cloned"
                )
            except subprocess.CalledProcessError:
                taf_logger.error("Repo {}: cannot clone from url {}", self.name, url)
            else:
                break

    def clone_or_pull(self, branches=None, only_fetch=False):
        """
        Clone or fetch the specified branch for the given repo.
        Return old and new HEAD.
        """
        if branches is None:
            branches = ["master"]
        taf_logger.debug(
            "Repo {}: cloning or pulling branches {}", self.name, ", ".join(branches)
        )

        old_head = self.head_commit_sha()
        if old_head is None:
            taf_logger.debug("Repo {}: old head sha is {}", self.name, old_head)
            try:
                self.clone()
            except subprocess.CalledProcessError:
                taf_logger.error("Repo {}: could not clone repo", self.name)
                raise CloneRepoException(self.url)
        else:
            try:
                for branch in branches:
                    if only_fetch:
                        self._git("fetch", "origin", f"{branch}:{branch}")
                    else:
                        self._git("pull", "origin", branch)
                    taf_logger.info(
                        "Repo {}: successfully fetched branch {}", self.name, branch
                    )
            except subprocess.CalledProcessError as e:
                if "fatal" in e.stdout:
                    raise FetchException(self.path)
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
        """Create local branch by checking it if it does not exist out and making sure
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
            self._git("diff --cached --exit-code --shortstat")
        except subprocess.CalledProcessError:
            run("git", "-C", self.path, "commit", "--quiet", "-m", message)
        return self._git("rev-parse HEAD")

    def commit_empty(self, message):
        run("git", "-C", self.path, "commit", "--quiet", "--allow-empty", "-m", message)
        return self._git("rev-parse HEAD")

    def commits_on_branch_and_not_other(
        self, branch1, branch2, include_branching_commit=False
    ):
        """
        Meant to find commits belonging to a branch which branches off of
        a commit from another branch. For example, to find only commits
        on a speculative branch and not on the master branch.
        """

        taf_logger.debug(
            "Repo {}: finding commits which are on branch {}, but not on branch {}",
            self.name,
            branch1,
            branch2,
        )
        commits = self._git(
            "log {} --not {} --no-merges --format=format:%H", branch1, branch2
        )
        commits = commits.split("\n") if commits else []
        if include_branching_commit:
            branching_commit = self._git("rev-list -n 1 {}~1", commits[-1])
            commits.append(branching_commit)
        taf_logger.debug("Repo {}: found the following commits: {}", self.name, commits)
        return commits

    def delete_local_branch(self, branch_name, force=False):
        """Deletes local branch."""
        flag = "-D" if force else "-d"
        self._git(f"branch {flag} {branch_name}")

    def delete_remote_branch(self, branch_name, remote=None):
        if remote is None:
            remote = self.remotes[0]
        self._git(f"push {remote} --delete {branch_name}")

    def get_commits_date(self, commit):
        date = self._git("show -s --format=%at {}", commit)
        return date.split(" ", 1)[0]

    def get_commit_message(self, commit):
        """Returns commit message of the given commit"""
        return self._git("log --format=%B -n 1 {}", commit).strip()

    def get_commit_sha(self, behind_head):
        """Get commit sha of HEAD~{behind_head}"""
        return self._git("rev-parse HEAD~{}", behind_head)

    def get_json(self, commit, path):
        s = self.get_file(commit, path)
        return json.loads(s)

    def get_file(self, commit, path):
        path = Path(path).as_posix()
        return self._git("show {}:{}", commit, path)

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
        except subprocess.CalledProcessError:
            return None

    def delete_branch(self, branch_name):
        self._git("branch -D {}", branch_name)

    def diff_between_revisions(self, revision1=EMPTY_TREE, revision2="HEAD"):
        return self._git("diff --name-status {} {}", revision1, revision2)

    def has_remote(self):
        return bool(self._git("remote"))

    def head_commit_sha(self):
        """Finds sha of the commit to which the current HEAD points"""
        try:
            return self._git("rev-parse HEAD")
        except subprocess.CalledProcessError:
            return None

    def fetch(self, fetch_all=False, branch=None, remote="origin"):
        if fetch_all:
            self._git("fetch --all")
        else:
            if branch is None:
                branch = ""
            self._git("fetch {} {}", remote, branch)

    def get_current_branch(self):
        """Return current branch."""
        return self._git("rev-parse --abbrev-ref HEAD").strip()

    def get_merge_base(self, branch1, branch2):
        """Finds the best common ancestor between two branches"""
        return self._git(f"merge-base {branch1} {branch2}")

    def get_tracking_branch(self, branch=""):
        """Returns tracking branch name in format origin/branch-name or None if branch does not
        track remote branch.
        """
        try:
            return self._git(f"rev-parse --abbrev-ref {branch}@{{u}}")
        except subprocess.CalledProcessError:
            return None

    def init_repo(self, bare=False):
        if self._path.is_dir():
            self._path.mkdir(exist_ok=True, parents=True)
        flag = "--bare" if bare else ""
        self._git(f"init {flag}")
        if self.repo_urls is not None and len(self.repo_urls):
            self._git("remote add origin {}", self.repo_urls[0])

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

    def list_commits(self, branch="", **kwargs):
        params = []
        for name, value in kwargs.items():
            params.append(f"--{name}={value}")

        return self._git("log {} {}", branch, " ".join(params)).split("\n")

    def list_commit_shas(self, branch="master"):
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

    def list_modified_files(self, path=None):
        diff_command = "diff --name-status"
        if path is not None:
            diff_command = f"{diff_command} {path}"
        modified_files = self._git(diff_command).split("\n")
        file_names = []
        for modified_file in modified_files:
            # ignore warning lines
            if len(modified_file) and modified_file[0] in ["A", "M", "D"]:
                file_names.append(modified_file.split(maxsplit=1)[1])
        return file_names

    def list_untracked_files(self, path=None):
        ls_command = "ls-files --others"
        if path is not None:
            ls_command = f"{ls_command} {path}"
        untracked_files = self._git(ls_command).split("\n")
        return [
            untracked_file for untracked_file in untracked_files if len(untracked_file)
        ]

    def merge_commit(self, commit):
        self._git("merge {}", commit)

    def pull(self):
        """Pull current branch"""
        self._git("pull")

    def push(self, branch=None, set_upstream=False, force=False):
        """Push all changes"""
        if branch is None:
            branch = self.get_current_branch()
        upstream_flag = "-u" if set_upstream else ""
        force_flag = "-f" if force else ""
        self._git("push {} {} origin {}", upstream_flag, force_flag, branch)

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
        except subprocess.CalledProcessError:
            taf_logger.info(
                "Auth repo {}: {} not available at revision {}",
                self.name,
                os.path.basename(path),
                commit,
            )
        except json.decoder.JSONDecodeError:
            taf_logger.info(
                "Auth repo {}: {} not a valid json at revision {}",
                self.name,
                os.path.basename(path),
                commit,
            )

    def set_remote_url(self, new_url, remote="origin"):
        self._git(f"remote set-url {remote} {new_url}")

    def set_upstream(self, branch_name):
        self._git("branch -u origin/{}", branch_name)

    def something_to_commit(self):
        """Checks if there are any uncommitted changes"""
        uncommitted_changes = self._git("status --porcelain")
        return bool(uncommitted_changes)

    def synced_with_remote(self, branch="master"):
        """Checks if local branch is synced with its remote branch"""
        # check if the latest local commit matches
        # the latest remote commit on the specified branch
        tracking_branch = self.get_tracking_branch(branch)
        if not tracking_branch:
            return False

        try:
            local_commit = self._git(f"rev-parse {branch}")
        except subprocess.CalledProcessError as e:
            if "unknown revision or path not in the working tree" not in e.output:
                raise e
            local_commit = None

        try:
            remote_commit = self._git(f"rev-parse {tracking_branch}")
        except subprocess.CalledProcessError as e:
            if "unknown revision or path not in the working tree" not in e.output:
                raise e
            remote_commit = None

        return local_commit == remote_commit

    def top_commit_of_branch(self, branch):
        return self._git(f"rev-parse {branch}")


class NamedGitRepository(GitRepository):
    def __init__(
        self,
        root_dir,
        repo_name,
        repo_urls=None,
        additional_info=None,
        default_branch="master",
        *args,
        **kwargs,
    ):
        """
    Args:
      root_dir: the root directory
      repo_name: repository's path relative to the root directory root_dir
      repo_urls: repository's urls (optional)
      additional_info: a dictionary containing other data (optional)
      default_branch: repository's default branch
    path is the absolute path to this repository. It is set by joining
    root_dir and repo_name.
    """
        self.root_dir = root_dir
        path = _get_repo_path(root_dir, repo_name)
        super().__init__(
            path,
            repo_name=repo_name,
            repo_urls=repo_urls,
            additional_info=additional_info,
            default_branch=default_branch,
        )


def _get_repo_path(root_dir, repo_name):
    """
  get the path to a repo and ensure it is valid.
  (since this is coming from potentially untrusted data)
  """
    _validate_repo_name(repo_name)
    repo_dir = str((Path(root_dir) / (repo_name or "")))
    if not repo_dir.startswith(repo_dir):
        taf_logger.error("Repo {}: repository name is not valid", repo_name)
        raise InvalidRepositoryError(f"Invalid repository name: {repo_name}")
    return repo_dir


_repo_name_re = re.compile(r"^\w[\w_-]*/\w[\w_-]*$")


def _validate_repo_name(repo_name):
    """ Ensure the repo name is not malicious """
    match = _repo_name_re.match(repo_name)
    if not match:
        taf_logger.error("Repo {}: repository name is not valid", repo_name)
        raise InvalidRepositoryError(
            "Repository name must be in format namespace/repository "
            "and can only contain letters, numbers, underscores and "
            f'dashes, but got "{repo_name}"'
        )


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


def _validate_url(url):
    """ ensure valid URL """
    for _url_re in [_http_fttp_url, _ssh_url]:
        match = _url_re.match(url)
        if match:
            return
    taf_logger.error("Repository URL ({}) is not valid", url)
    raise InvalidRepositoryError(
        f'Repository URL must be a valid URL, but got "{url}".'
    )
