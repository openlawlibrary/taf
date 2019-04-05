import subprocess
import os


def run(*command, **kwargs):
  """Run a command and return its output"""
  if len(command) == 1 and isinstance(command[0], str):
    command = command[0].split()
  print(*command)
  command = [word.format(**os.environ) for word in command]
  try:
    options = dict(stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=True,
      universal_newlines=True)
    options.update(kwargs)
    completed = subprocess.run(command, **options)
  except subprocess.CalledProcessError as err:
    if err.stdout:
        print(err.stdout)
    if err.stderr:
        print(err.stderr)
    print('Command "{}" returned non-zero exit status {}'.format(' '.join(command),
                                                                     err.returncode))
    raise err
  if completed.stdout:
      print(completed.stdout)
  return completed.stdout.rstrip() if completed.returncode == 0 else None


class GitRepo(object):

  def __init__(self, repo_path):
    self.repo_path = repo_path


  def _git(self, cmd):
    return run(f'git -C {self.repo_path} {cmd}')


  def all_commits(self):
    commits = self._git(f'rev-list').strip()
    if not commits:
      return commits
    commits = commits.split('\n')
    commits.reverse()
    return commits

  def all_commits_since_commit(self, since_commit):
    commits = self._git(f'rev-list {since_commit}..HEAD').strip()
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
      self._git(f'checkout {branch_name}')
    except subprocess.CalledProcessError as e:
      if create:
        self._git(f'checkout -b {branch_name}')
      else:
        raise(e)


  def checkout_commit(self, branch, commit_sha):
    self._git(f'update-ref refs/heads/{branch} {commit_sha}')


  def commit(self, message):
    """Create a commit with the provided message
    on the currenly checked out branch"""
    self._git('add -A')
    try:
      self._git('diff --cached --exit-code --shortstat')
    except subprocess.CalledProcessError:
      run('git', '-C', self.repo_path, 'commit', '--quiet', '-m', message)
    return self._git('rev-parse HEAD')


  def current_branch(self):
    return self._git('rev-parse --abbrev-ref HEAD')


  def diff(self, branch1, branch2):
    return self._git(f'diff {branch1} {branch2}')


  def diff_compared_to_origin(self, branch):
    return self.diff(branch, f'origin/{branch}')


  def fetch(self, fetch_all=False):
    if fetch_all:
      self._git('fetch --all')
    else:
      self._git('fetch')


  def list_files_at_revision(self, commit):
    file_names = self._git(f'ls-tree -r {commit} --name-only')
    list_of_files = []
    if not file_names:
      return list_of_files
    for file_in_repo in file_names.split('\n'):
      if '/' in file_in_repo:
        file_in_repo = file_in_repo.rsplit('/')[-1]
        list_of_files.append(file_in_repo)
    return list_of_files


  def file_exists_at_revision(self, commit, file_name):
    return file_name in self.list_files_at_revision(commit)


  def head_commit_sha(self):
    """Finds sha of the commit to which the current HEAD points"""
    return self._git('rev-parse HEAD')


  def is_git_repository(self):
    return self._git('rev-parse --is-inside-work-tree') == 'true'


  def previous_commit_sha(self):
    """Finds sha of the commit which is the parent of the top commit"""
    commits = self._git('rev-list --parents -n 1 HEAD')
    if commits:
      head_and_parent = commits.split(' ')
      if len(head_and_parent) > 1:
        return head_and_parent[1]
    return None


  def reset_hard(self, num=1):
    self._git(f'reset --hard HEAD~{num}')


  def show_file_at_revision(self, commit, file_path):
    return self._git(f'show  {commit}:{file_path}')


  def merge_branch(self, branch):
    self._git(f'merge {branch}')


class BareGitRepo(GitRepo):


  def clone(self, url):
    dir_name = f'{url.rsplit("/", 1)[-1]}.git'
    new_path = os.path.join(self.repo_path, dir_name)
    # just during development
    if not os.path.isdir(new_path):
      self._git(f'clone --bare {url}')
    self.repo_path = new_path
