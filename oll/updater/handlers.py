import os
import tuf
import securesystemslib
import logging
import tuf.exceptions
import six
import errno
import tempfile
import shutil
import glob
import tuf.client.handlers as handlers
from git import GitRepo, BareGitRepo


class GitMetadataUpdater(handlers.MetadataUpdater):


  def __init__(self, mirrors, repository_directory):
    super(GitMetadataUpdater, self).__init__(mirrors, repository_directory)
    # validation_auth_repo is a freshly cloned
    # bare repository. It is cloned to a temporary
    # directory that should be removed once the update
    # is completed
    auth_url = mirrors['mirror1']['url_prefix']
    self._clone_validation_repo(auth_url)
    # users_auth_repo is the authentication repository
    # located on the users machine which needs to be
    # updated
    self.repository_directory = repository_directory
    # create current and previous directories
    metadata_path = os.path.join(self.repository_directory, 'metadata')
    self.current_path = os.path.join(metadata_path, 'current')
    self.previous_path = os.path.join(metadata_path, 'previous')

    os.mkdir(self.current_path)
    os.mkdir(self.previous_path)

    for filename in glob.glob(os.path.join(metadata_path, '*.json')):
      shutil.copy(filename, self.current_path)
      shutil.copy(filename, self.previous_path)

    self.users_auth_repo = GitRepo(repository_directory)
    self.users_auth_repo.is_git_repository()
    self.users_auth_repo.checkout_branch('master')
    self._init_commits()


  def _clone_validation_repo(self, url):
    temp_dir = tempfile.gettempdir()
    self.validation_auth_repo = BareGitRepo(temp_dir)
    self.validation_auth_repo.clone(url)
    self.validation_auth_repo.fetch(fetch_all=True)


  def _init_commits(self):
    users_head_sha = self.users_auth_repo.head_commit_sha()
    # find all commits after the top commit of the
    # client's local authentication repository
    self.commits = self.validation_auth_repo.all_commits_since_commit(users_head_sha)
    # insert the current one at the beginning of the list
    self.commits.insert(0, users_head_sha)

    # assuming that the user's directory exists for now
    self.commits_indexes = {}

    for file_name in self.users_auth_repo.list_files_at_revision(users_head_sha):
      self.commits_indexes[file_name] = 0


  def get_mirrors(self, remote_filename):
    commit = self.commits_indexes.get(remote_filename, -1)
    return self.commits[commit+1::]

  def get_metadata_file(self, file_mirror, _filename, _upperbound_filelength):
    commit = file_mirror
    metadata = self.validation_auth_repo.show_file_at_revision(
        commit, f'metadata/{_filename}')

    temp_file_object = securesystemslib.util.TempFile()
    temp_file_object.write(metadata.encode())

    return temp_file_object


  def on_successful_update(self, filename, location):
    last_index = len(self.commits) - 1
    self.commits_indexes[filename] = self.commits.index(location)


  def _cleaup(self):
    shutil.rmtree(self.current_path)
    shutil.rmtree(self.previous_path)


  def on_unsuccessful_update(self, filename):
    self._cleaup()


  def update_done(self):
    # the only metadata file that is always updated
    # regardless of if it changed or not is timestamp
    # so we can check if timestamp was updated a certain
    # number of times
    last_index = len(self.commits) - 1
    timestamp_commit = self.commits_indexes['timestamp.json']
    return last_index == timestamp_commit
