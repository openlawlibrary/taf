from taf.GitRepository import GitRepository

class AuthenticationRepo(GitRepository):

  def __init__(self, root_dir, repo_path=None, repo_urls=None, bare=False):
    super().__init__(root_dir, repo_path, repo_urls)
    self.bare = bare

  def all_commits_since_commit(self, since_commit):
    commits = self._git(f'rev-list {since_commit}..HEAD').strip()
    if not commits:
      return []
    commits = commits.split('\n')
    commits.reverse()
    return commits

  def get_commits_date(self, commit):
    date = self._git(f'show -s --format=%at {commit}')
    return date.split(' ', 1)[0]

  def list_files_at_revision(self, commit, path=''):
    if path is None:
      path = ''
    cmd = f'ls-files {commit}'
    file_names = self._git(f'ls-files {commit} {path}')
    list_of_files = []
    if not file_names:
      return list_of_files
    for file_in_repo in file_names.split('\n'):
      if '/' in file_in_repo:
        file_in_repo = file_in_repo.rsplit('/')[-1]
        list_of_files.append(file_in_repo)
    return list_of_files

  def clone(self):
    super().clone(self.bare)
