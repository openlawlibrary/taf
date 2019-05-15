import os
from taf.GitRepository import GitRepository

class AuthenticationRepo(GitRepository):

  def __init__(self, root_dir, repo_path=None, repo_urls=None, bare=False):
    super().__init__(root_dir, repo_path, repo_urls)
    self.bare = bare

  def all_commits_since_commit(self, since_commit):
    if since_commit is not None:
      commits = self._git(f'rev-list {since_commit}..HEAD').strip()
    else:
      commits = self._git(f'log --format=format:%H').strip()
    if not commits:
      return []
    commits = commits.split('\n')
    commits.reverse()
    return commits

  def clone_or_pull_up_to_commit(self, commit):
    if not self.is_git_repository():
      self.clone('--no-checkout')
      self.hard_reset(commit)
    else:
      self.fetch()
      self.merget_commit(commit)

  def clone(self, *args):
    bare = '--bare' if self.bare else ''
    super().clone(bare, *args)

  def get_commits_date(self, commit):
    date = self._git(f'show -s --format=%at {commit}')
    return date.split(' ', 1)[0]

  def list_files_at_revision(self, commit, path=''):
    if path is None:
      path = ''
    file_names = self._git(f'ls-tree -r --name-only {commit}')
    list_of_files = []
    if not file_names:
      return list_of_files
    for file_in_repo in file_names.split('\n'):
      if not file_in_repo.startswith(path):
        continue
      file_in_repo = os.path.relpath(file_in_repo, path)
      list_of_files.append(file_in_repo)
    return list_of_files

  def hard_reset(self, commit):
    self._git(f'reset --hard {commit}')

  def merget_commit(self, commit):
    self._git(f'merge {commit}')
