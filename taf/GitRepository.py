import json
import os
import shutil
import subprocess
from pathlib import Path

from taf.utils import run


class GitRepository(object):

  def __init__(self, root_dir, target_path=None, repo_urls=None, additional_info=None, bare=False):
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
    self.repo_path = str((Path(root_dir) / (target_path or '')).resolve())
    self.repo_urls = repo_urls
    self.additional_info = additional_info
    self.bare = bare

  @property
  def name(self):
    return os.path.basename(self.repo_path)

  def _git(self, cmd, *args):
    """Call git commands in subprocess

    E.G.:
      self._git('checkout {}', branch_name)
    """
    if len(args):
      cmd = cmd.format(*args)
    return run('git -C {} {}'.format(self.repo_path, cmd))

  def all_commits_since_commit(self, since_commit):
    if since_commit is not None:
      commits = self._git('rev-list {}..HEAD', since_commit).strip()
    else:
      commits = self._git('log --format=format:%H').strip()
    if not commits:
      return []
    commits = commits.split('\n')
    commits.reverse()
    return commits

  def checkout_branch(self, branch_name, create=False):
    """Check out the specified branch. If it does not exists and
    the create parameter is set to True, create a new branch.
    If the branch does not exist and create is set to False,
    raise an exception."""
    try:
      self._git('checkout {}', branch_name)
    except subprocess.CalledProcessError as e:
      if create:
        self.create_and_checkout_branch(branch_name)
      else:
        raise(e)

  def clone_or_pull_up_to_commit(self, commit):
    if not self.is_git_repository():
      self.init_repo()
    self.fetch()
    self.merge_commit(commit)

  def clone(self, no_checkout=False, from_filesystem=True):
    # TODO this creates something like smc-law/smc-law instead of just smc-law
    shutil.rmtree(self.repo_path, True)
    os.makedirs(self.repo_path, exist_ok=True)
    if self.repo_urls is None:
      raise Exception('Cannot clone repository. No urls were specified')
    params = ''
    if self.bare:
      params = '--bare'
    elif no_checkout:
      params = '--no-checkout'
    for url in self.repo_urls:
      try:
        if from_filesystem:
          url = url.replace('/', os.sep)

        self._git('clone {} . {}', url, params)
      except subprocess.CalledProcessError:
        print('Cannot clone repository {} from url {}'.format(self.name, url))
      else:
        break

  def checkout_branch(self, branch_name):
    self._git('checkout {}', branch_name)

  def create_and_checkout_branch(self, branch_name):
    self._git('checkout -b {}', branch_name)

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

    commits = self._git('log {} --not {} --no-merges --format=format:%H', branch1, branch2)
    commits = commits.split('\n') if commits else []
    if include_branching_commit:
      branching_commit = self._git('rev-list -n 1 {}~1', commits[-1])
      commits.append(branching_commit)

    return commits

  def get_commits_date(self, commit):
    date = self._git('show -s --format=%at {}', commit)
    return date.split(' ', 1)[0]

  def get_json(self, commit, path):
    s = self.get_file(commit, path)
    return json.loads(s)

  def get_file(self, commit, path):
    return self._git('show {}:{}', commit, path)

  def head_commit_sha(self):
    """Finds sha of the commit to which the current HEAD points"""
    try:
      return self._git('rev-parse HEAD')
    except subprocess.CalledProcessError:
      return None

  def fetch(self, fetch_all=False):
    if fetch_all:
      self._git('fetch --all')
    else:
      self._git('fetch')

  def init_repo(self):
    if not os.path.isdir(self.repo_path):
      os.makedirs(self.repo_path, exist_ok=True)
    self._git('init')
    self._git('remote add origin {}', self.repo_urls[0])

  def is_git_repository(self):
    try:
      self._git('rev-parse --git-dir')
    except subprocess.CalledProcessError:
      return False
    return True

  def list_files_at_revision(self, commit, path=''):
    if path is None:
      path = ''
    file_names = self._git('ls-tree -r --name-only {}', commit)
    list_of_files = []
    if not file_names:
      return list_of_files
    for file_in_repo in file_names.split('\n'):
      if not file_in_repo.startswith(path):
        continue
      file_in_repo = os.path.relpath(file_in_repo, path)
      list_of_files.append(file_in_repo)
    return list_of_files

  def merge_commit(self, commit):
    self._git('merge {}', commit)

  def pull(self):
    """Pull current branch"""
    self._git('pull')

  def push(self, branch=''):
    """Push all changes"""
    try:
      self._git('push origin {}', branch).strip()
    except subprocess.CalledProcessError:
      self._git('--set-upstream origin {}', branch).strip()
