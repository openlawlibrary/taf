import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import taf.log
import taf.settings as settings
from taf.exceptions import InvalidRepositoryError
from taf.utils import run

logger = taf.log.get_logger(__name__)


class GitRepository(object):

  def __init__(self, repo_path, repo_urls=None, additional_info=None, default_branch='master'):
    """
    Args:
      repo_path: repository's path
      repo_urls: repository's urls (optional)
      additional_info: a dictionary containing other data (optional)
      default_branch: repository's default branch
    """
    self.repo_path = str(repo_path)
    self.default_branch = default_branch
    if repo_urls is not None:
      if settings.update_from_filesystem is False:
        for url in repo_urls:
          _validate_url(url)
      else:
        repo_urls = [os.path.normpath(os.path.join(self.repo_path, url)) if
                     not os.path.isabs(url) else url
                     for url in repo_urls]
    self.repo_urls = repo_urls
    self.additional_info = additional_info
    self.repo_name = os.path.basename(self.repo_path)

  _remotes = None

  @property
  def remotes(self):
    if self._remotes is None:
      self._remotes = self._git('remote').split('\n')
    return self._remotes

  @property
  def is_git_repository_root(self):
    """Check if path is git repository."""
    git_path = Path(self.repo_path) / '.git'
    return self.is_git_repository and (git_path.is_dir() or git_path.is_file())

  @property
  def is_git_repository(self):
    try:
      self._git('rev-parse --git-dir')
      return True
    except subprocess.CalledProcessError:
      return False

  @property
  def initial_commit(self):
    return self._git('rev-list --max-parents=0 HEAD').strip() if self.is_git_repository else None

  def is_remote_branch(self, branch_name):
    for remote in self.remotes:
      if branch_name.startswith(remote + '/'):
        return True
    return False

  def _git(self, cmd, *args, **kwargs):
    """Call git commands in subprocess
    e.g.:
      self._git('checkout {}', branch_name)
    """
    log_error = kwargs.pop('log_error', False)
    log_error_msg = kwargs.pop('log_error_msg', '')
    reraise_error = kwargs.pop('reraise_error', False)
    log_success_msg = kwargs.pop('log_success_msg', '')

    if len(args):
      cmd = cmd.format(*args)
    command = 'git -C {} {}'.format(self.repo_path, cmd)
    if log_error or log_error_msg:
      try:
        result = run(command)
        if log_success_msg:
          logger.debug('Repo %s:' + log_success_msg, self.repo_name)
      except subprocess.CalledProcessError as e:
        if log_error_msg:
          logger.error(log_error_msg)
        else:
          logger.error('Repo %s: error occurred while executing %s:\n%s',
                       self.repo_name, command, e.output)
        if reraise_error:
          raise
    else:
      result = run(command)
      if log_success_msg:
        logger.debug('Repo %s: ' + log_success_msg, self.repo_name)
    return result

  def all_commits_since_commit(self, since_commit):
    if since_commit is not None:
      commits = self._git('rev-list {}..HEAD', since_commit).strip()
    else:
      commits = self._git('log --format=format:%H').strip()
    if not commits:
      commits = []
    else:
      commits = commits.split('\n')
      commits.reverse()

    if since_commit is not None:
      logger.debug('Repo %s: found the following commits after commit %s: %s', self.repo_name,
                   since_commit, ', '.join(commits))
    else:
      logger.debug('Repo %s: found the following commits: %s', self.repo_name, ', '.join(commits))
    return commits

  def all_fetched_commits(self, branch='master'):
    commits = self._git('rev-list ..origin/{}', branch).strip()
    if not commits:
      commits = []
    else:
      commits = commits.split('\n')
      commits.reverse()
    logger.debug('Repo %s: fetched the following commits %s', self.repo_name, ', '.join(commits))
    return commits


  def branch_local_name(self, remote_branch_name):
    """Strip remote from the given remote branch"""
    for remote in self.remotes:
      if remote_branch_name.startswith(remote + '/'):
        return remote_branch_name.split('/', 1)[1]

  def checkout_branch(self, branch_name, create=False):
    """Check out the specified branch. If it does not exists and
    the create parameter is set to True, create a new branch.
    If the branch does not exist and create is set to False,
    raise an exception."""
    try:
      self._git('checkout {}', branch_name, log_error=True, reraise_error=True,
                log_success_msg='checked out branch {}'.format(branch_name))
    except subprocess.CalledProcessError as e:
      if create:
        self.create_and_checkout_branch(branch_name)
      else:
        raise(e)

  def clean(self):
    self._git('clean -fd')

  def clone(self, no_checkout=False, bare=False):

    logger.info('Repo %s: cloning repository', self.repo_name)
    shutil.rmtree(self.repo_path, True)
    os.makedirs(self.repo_path, exist_ok=True)
    if self.repo_urls is None:
      raise Exception('Cannot clone repository. No urls were specified')
    params = ''
    if bare:
      params = '--bare'
    elif no_checkout:
      params = '--no-checkout'
    for url in self.repo_urls:
      try:
        self._git('clone {} . {}', url, params, log_success_msg='successfully cloned')
      except subprocess.CalledProcessError:
        logger.error('Repo %s: cannot clone from url %s', self.repo_name, url)
      else:
        break

  def create_and_checkout_branch(self, branch_name):
    self._git('checkout -b {}', branch_name,  log_success_msg='created and checked out branch {}'.
              format(branch_name, log_error=True, reraise_error=True))

  def checkout_commit(self, commit):
    self._git('checkout {}', commit, log_success_msg='checked out commit {}'.format(commit))

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

    logger.debug('Repo %s: finding commits which are on branch %s, but not on branch %s',
                 self.repo_name, branch1, branch2)
    commits = self._git('log {} --not {} --no-merges --format=format:%H', branch1, branch2)
    commits = commits.split('\n') if commits else []
    if include_branching_commit:
      branching_commit = self._git('rev-list -n 1 {}~1', commits[-1])
      commits.append(branching_commit)
    logger.debug('Repo %s: found the following commits: %s', self.repo_name, commits)
    return commits

  def get_commits_date(self, commit):
    date = self._git('show -s --format=%at {}', commit)
    return date.split(' ', 1)[0]

  def get_json(self, commit, path):
    s = self.get_file(commit, path)
    return json.loads(s)

  def get_file(self, commit, path):
    return self._git('show {}:{}', commit, path)

  def get_remote_url(self):
    try:
      return self._git('config --get remote.origin.url').strip()
    except subprocess.CalledProcessError:
      return None

  def delete_branch(self, branch_name):
    self._git('branch -D {}', branch_name)

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
    if self.repo_urls is not None and len(self.repo_urls):
      self._git('remote add origin {}', self.repo_urls[0])

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

  def list_commits(self, **kwargs):
    params = []
    for name, value in kwargs.items():
      params.append('--{}={}'.format(name, value))

    return self._git('log {}', ' '.join(params)).split('\n')

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

  def rename_branch(self, old_name, new_name):
    self._git('branch -m {} {}', old_name, new_name)

  def reset_num_of_commits(self, num_of_commits, hard=False):
    flag = '--hard' if hard else '--soft'
    self._git('reset {} HEAD~{}'.format(flag, num_of_commits))

  def reset_to_commit(self, commit, hard=False):
    flag = '--hard' if hard else '--soft'
    self._git('reset {} {}'.format(flag, commit))

  def reset_to_head(self):
    self._git('reset --hard HEAD')

  def set_upstream(self, branch_name):
    self._git('branch -u origin/{}', branch_name)

class NamedGitRepository(GitRepository):

  def __init__(self, root_dir, repo_name, repo_urls=None, additional_info=None,
               default_branch='master'):
    """
    Args:
      root_dir: the root directory
      repo_name: repository's path relative to the root directory root_dir
      repo_urls: repository's urls (optional)
      additional_info: a dictionary containing other data (optional)
      default_branch: repository's default branch
    repo_path is the absolute path to this repository. It is set by joining
    root_dir and repo_name.
    """
    repo_path = _get_repo_path(root_dir, repo_name)
    super().__init__(repo_path, repo_urls, additional_info, default_branch)
    self.repo_name = repo_name


def _get_repo_path(root_dir, repo_name):
  """
  get the path to a repo and ensure it is valid.
  (since this is coming from potentially untrusted data)
  """
  _validate_repo_name(repo_name)
  repo_dir = str((Path(root_dir) / (repo_name or '')))
  if not repo_dir.startswith(repo_dir):
    logger.error('Repo %s: repository name is not valid', repo_name)
    raise InvalidRepositoryError('Invalid repository name: {}'.format(repo_name))
  return repo_dir


_repo_name_re = re.compile(r'^\w[\w_-]*/\w[\w_-]*$')


def _validate_repo_name(repo_name):
  """ Ensure the repo name is not malicious """
  match = _repo_name_re.match(repo_name)
  if not match:
    logger.error('Repo %s: repository name is not valid', repo_name)
    raise InvalidRepositoryError('Repository name must be in format namespace/repository '
                                 'and can only contain letters, numbers, underscores and '
                                 'dashes, but got "{}"'.format(repo_name))


_http_fttp_url = re.compile(
    r'^(?:http|ftp)s?://'  # http:// or https://
    # domain...
    r'(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+(?:[A-Z]{2,6}\.?|[A-Z0-9-]{2,}\.?)|'
    r'localhost|'  # localhost...
    r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})'  # ...or ip
    r'(?::\d+)?'  # optional port
    r'(?:/?|[/?]\S+)$', re.IGNORECASE)

_ssh_url = re.compile(r'((git|ssh|http(s)?)|(git@[\w\.]+))(:(//)?)([\w\.@\:/\-~]+)(\.git)?(/)?')


def _validate_url(url):
  """ ensure valid URL """
  for _url_re in [_http_fttp_url, _ssh_url]:
    match = _url_re.match(url)
    if match:
      return
  logger.error('Repository URL (%s) is not valid', url)
  raise InvalidRepositoryError('Repository URL must be a valid URL, but got "{}".'.format(url))
