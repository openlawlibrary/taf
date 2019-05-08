import json
import os
import subprocess

from .utils import run


class GitRepository(object):

  def __init__(self, root_dir, target_path=None, repo_urls=None, additional_info=None):
    """
    Args:
      root_dir: the root directory, target_path is relative to it
      target_path: repository's relative path, as specified in targets.json
      and mirrors.json (optional)
      repo_urls: repository's urls (optional)
      additional_info: a dictionary containing other data (optional)
    repo_path is the absolute path to this repository. If target path is not None,
    it is set by joining root_dir and target_path. Otherwise, it is set to just
    root_dir.
    """
    self.target_path = target_path
    if target_path is not None:
      self.repo_path = os.path.join(root_dir, target_path.replace('/', os.sep))
    else:
      self.repo_path = root_dir
    self.repo_path = os.path.normpath(self.repo_path)
    self.repo_urls = repo_urls
    self.additional_info = additional_info

  @property
  def name(self):
    return os.path.basename(self.repo_path)

  def _git(self, cmd):
    return run(f'git -C {self.repo_path} {cmd}')

  def checkout_branch(self, branch_name, create=False):
    """Check out the specified branch. If it does not exists and
    the create parameter is set to True, create a new branch.
    If the branch does not exist and create is set to False,
    raise an exception."""
    try:
      self._git(f'checkout {branch_name}')
    except subprocess.CalledProcessError as e:
      if create:
        self.create_and_checkout_branch(branch_name)
      else:
        raise(e)

  def create_and_checkout_branch(self, branch_name):
    self._git(f'checkout -b {branch_name}')

  def commit(self, message):
    """Create a commit with the provided message
    on the currently checked out branch"""
    self._git('add -A')
    try:
      self._git('diff --cached --exit-code --shortstat')
    except subprocess.CalledProcessError:
      run('git', '-C', self.repo_path, 'commit', '--quiet', '-m', message)
    return self._git('rev-parse HEAD')

  def commits_on_branch_and_not_other(self, branch1, branch2, include_branching_commit=False):
    """
    Meant to find commits belonging to a branch which branches off of
    a commit from another branch. For example, to find only commits
    on a speculative branch and not on the master branch.
    """

    commits = self._git(f'log {branch1} --not {branch2} --no-merges --format=format:%H')
    commits = commits.split('\n') if commits else []
    if include_branching_commit:
      branching_commit = self._git(f'rev-list -n 1 {commits[-1]}~1')
      commits.append(branching_commit)

    return commits

  def get_json(self, commit, path):
    s = self.get_file(commit, path)
    return json.loads(s)

  def get_file(self, commit, path):
    return self._git(f'show {commit}:{path}')

  def head_commit_sha(self):
    """Finds sha of the commit to which the current HEAD points"""
    return self._git('rev-parse HEAD')

  def is_git_repository(self):
    try:
      self._git('rev-parse --git-dir')
    except subprocess.CalledProcessError:
      return False
    return True

  def pull(self):
    """Pull current branch"""
    self._git('pull')

  def push(self, branch=''):
    """Push all changes"""
    try:
      self._git(f'push origin {branch}'.strip())
    except subprocess.CalledProcessError:
      self._git(f'--set-upstream origin {branch}'.strip())
