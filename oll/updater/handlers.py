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
    """
    This class implements updating metadata stored in git repositories.
    The update process is still mostly handled by the updater. This
    class is only supposed to implement loading of metadata from
    a git repository and keeping track of the current commit.
    Since we do not want to change the clients repository until
    we know it is safe to use git pull, the update works as follows:
    - The repository containing the metadata files is cloned to the temp folder.
    - The most recent commit in the client's local repository is determined. Based
    on that all new commits (newer than the client's most recent one in the
    cloned repository) are found.
    - A commit is considered to be a TUF mirror. We keep track of the current commit.
    - This class is designed in such a way that for each subsequent call of the
    updater's refresh method the next commit is used as a mirror. There are many
    reasons why this is better than instantiating this class multiple time:
        - We would have to clone the repository again. Passing already created GitRepo
        object to this class would require more substantial changes of the updater.
        - We would have to either merge just one commit into the clients repository
        after one refresh is successfully finished, or we would need to pass in the
        current commit to this class - meaning that the updater would have to be modified.
    - The updater's method '_get_metadata_file' call 'get_mirrors'. It then iterates
    through these mirrors and tries to update a metadata file by downloading them
    from each mirror, until a valid metadata is downloaded. If none of the mirrors
    contains valid metadata, an exception is raised. So, what we want to do is to
    return the current commit, and just the current commit. This means that that an
    exception will be raised if the version of the metadata file at that commit
    is not valid.

    Attributes:
        - repository_directory: the client's local repositoy's location
        - current_path: path of the 'current' directory needed by the updater
        - previous_path: path of the 'previous' directory needed by the updater
        - validation_auth_repo: a fresh clone of the metadata repository. It is
        a bare git repository. An instance of the `BareGitRepo` class.
        - users_auth_repo: an instance of the `GitRepo` class. The user's current
        git repository.
        - commits: a list of commits, starting with the most recent commit in the
        user's repository. The following commits are those committed after the
        the top one if the client's repo.
        - commits_indexes: a dictionary which stores intex of the current commit
        per metadata file. The reason for separating the metadata files is that
        not all files are updated at the same time.

    """
    def __init__(self, mirrors, repository_directory):
        """
        Args:
        mirrors: is a dictionary which contains information about each mirror:
                    mirrors = {'mirror1': {'url_prefix': 'http://localhost:8001',
                                    'metadata_path': 'metadata',
                                    'targets_path': 'targets',
                                    'confined_target_dirs': ['']}}
        This dictionary is provided by the user of the updater and used to
        create an instance of the tuf updater.
        We use url_prefix to specify url of the git repository which we want to clone.

        repository_directory: the client's local repositoy's location

        """
        super(GitMetadataUpdater, self).__init__(mirrors, repository_directory)
        # validation_auth_repo is a freshly cloned bare repository.
        # It is cloned to a temporary directory that should be removed
        # once the update is completed
        auth_url = mirrors['mirror1']['url_prefix']
        self._clone_validation_repo(auth_url)
        # users_auth_repo is the authentication repository
        # located on the users machine which needs to be updated
        self.repository_directory = repository_directory

        # create current and previous directories and copy the metadata files
        # needed by the updater
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
        # TODO handle the case when the local repository does not
        # exist and needs to be cloned
        # for now, it is assumed that there is a local repository
        users_head_sha = self.users_auth_repo.head_commit_sha()
        # find all commits after the top commit of the
        # client's local authentication repository
        # TODO detect force-push removal of commits
        self.commits = self.validation_auth_repo. \
            all_commits_since_commit(users_head_sha)
        # insert the current one at the beginning of the list
        self.commits.insert(0, users_head_sha)

        self.commits_indexes = {}

        for file_name in self.users_auth_repo. \
                list_files_at_revision(users_head_sha):
            self.commits_indexes[file_name] = 0


    def get_mirrors(self, remote_filename):
        # return a list containing just the current commit
        commit = self.commits_indexes.get(remote_filename, -1)
        return [self.commits[commit+1]]

    def get_metadata_file(self, file_mirror, _filename, _upperbound_filelength):
        commit = file_mirror
        metadata = self.validation_auth_repo.show_file_at_revision(
            commit, f'metadata/{_filename}')

        temp_file_object = securesystemslib.util.TempFile()
        temp_file_object.write(metadata.encode())

        return temp_file_object


    def on_successful_update(self, filename, location):
        # after the is successfully completed, set the
        # next commit as current for the given file
        last_index = len(self.commits) - 1
        self.commits_indexes[filename] = self.commits.index(location)


    def cleanup(self):
        # this needs to be called after the update is finished
        # either successfully or unsuccessfully
        shutil.rmtree(self.current_path)
        shutil.rmtree(self.previous_path)


    def on_unsuccessful_update(self, filename):
        # TODO a error message
        pass


    def update_done(self):
        # the only metadata file that is always updated
        # regardless of if it changed or not is timestamp
        # so we can check if timestamp was updated a certain
        # number of times
        last_index = len(self.commits) - 1
        timestamp_commit = self.commits_indexes['timestamp.json']
        return last_index == timestamp_commit
