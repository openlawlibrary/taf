import os
import shutil
import tempfile
import time
from pathlib import Path

import securesystemslib
import tuf.client.handlers as handlers

from taf.exceptions import GitError
from taf.log import taf_logger
import taf.settings as settings
from taf.auth_repo import AuthenticationRepo, NamedAuthenticationRepo
from taf.exceptions import UpdateFailedError
from taf.git import GitRepository
from taf.utils import on_rm_error


class GitUpdater(handlers.MetadataUpdater):
    """
    This class implements parts of the update process specific to keeping
    metadata files and targets in a git repository. The vast majority of the
    update process is handled by TUF's updater. This class does not modify
    and of TUF's validation functionalities - it only handles loading of
    files.
    One substantial difference between our system and how TUF is designed lies in the
    fact that we want to validate every commit and not just check if the most recent
    one contains valid metadata. We want to check if the metadata was valid at the time
    when it was committed.

    Since we do not want to change the clients repository until
    we know it is safe to use git pull, the update works as follows:
    - The repository containing the metadata files is cloned to the temp folder.
    - The most recent commit in the client's local repository is determined. Based
    on that all new commits (newer than the client's most recent one in the
    cloned repository) are found.
    - A commit is considered to be a TUF mirror. We keep track of the current commit.
    - This class is designed in such a way that for each subsequent call of the
    updater's refresh method the next commit is used as a mirror. This is better than
    instantiating this class multiple times as that seems to require less modifications
    of TUF's code.
    - The updater's method '_get_metadata_file' call 'get_mirrors'. It then iterates
    through these mirrors and tries to update a metadata file by downloading them
    from each mirror, until a valid metadata is downloaded. If none of the mirrors
    contains valid metadata, an exception is raised. So, what we want to do is to
    return the current commit, and just the current commit. This means that that an
    exception will be raised if the version of the metadata file at that commit
    is not valid.
    - The same logic is used to handle targets.


    Attributes:
        - repository_directory: the client's local repository's location
        - current_path: path of the 'current' directory needed by the updater
        - previous_path: path of the 'previous' directory needed by the updater
        - validation_auth_repo: a fresh clone of the metadata repository. It is
        a bare git repository. An instance of the `BareGitRepo` class.
        - users_auth_repo: an instance of the `GitRepo` class. The user's current
        git repository.
        - commits: a list of commits, starting with the most recent commit in the
        user's repository. The following commits are those committed after the
        the top one if the client's repo.
        - commits_indexes: a dictionary which stores index of the current commit
        per metadata file. The reason for separating the metadata files is that
        not all files are updated at the same time.
    """

    @property
    def current_commit(self):
        return self.commits[self.current_commit_index]

    @property
    def previous_commit(self):
        return self.commits[self.current_commit_index - 1]

    def __init__(self, mirrors, repository_directory, repository_name):
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
        repository_directory: the client's local repository's location
        """
        super(GitUpdater, self).__init__(mirrors, repository_directory, repository_name)

        auth_url = mirrors["mirror1"]["url_prefix"]
        self.metadata_path = mirrors["mirror1"]["metadata_path"]
        self.targets_path = mirrors["mirror1"]["targets_path"]
        if settings.validate_repo_name:
            self.users_auth_repo = NamedAuthenticationRepo(
                repository_directory, repository_name, repo_urls=[auth_url]
            )
        else:
            users_repo_path = Path(repository_directory, repository_name)
            self.users_auth_repo = AuthenticationRepo(
                str(users_repo_path),
                self.metadata_path,
                self.targets_path,
                repo_urls=[auth_url],
            )

        self._clone_validation_repo(auth_url)
        repository_directory = Path(self.users_auth_repo.path)
        if repository_directory.exists():
            if not self.users_auth_repo.is_git_repository_root:
                if repository_directory.glob("*"):
                    raise UpdateFailedError(
                        f"{repository_directory} is not a git repository and is not empty"
                    )

        # validation_auth_repo is a freshly cloned bare repository.
        # It is cloned to a temporary directory that should be removed
        # once the update is completed

        self._init_commits()
        # users_auth_repo is the authentication repository
        # located on the users machine which needs to be updated
        self.repository_directory = str(repository_directory)

        self._init_metadata()

    def _init_commits(self):
        """
        Given a client's local repository which needs to be updated, creates a list
        of commits of the authentication repository newer than the most recent
        commit of the client's repository. These commits need to be validated.
        If the client's repository does not exist, all commits should be validated.
        We have to presume that the initial metadata is correct though (or at least
        the initial root.json).
        """
        # TODO check if users authentication repository is clean

        # load the last validated commit from the conf file
        if settings.overwrite_last_validated_commit:
            last_validated_commit = settings.last_validated_commit
        else:
            last_validated_commit = self.users_auth_repo.last_validated_commit
        try:
            commits_since = self.validation_auth_repo.all_commits_since_commit(
                last_validated_commit
            )
        except GitError as e:
            if "Invalid revision range" in e.output:
                taf_logger.error(
                    "Commit {} is not contained by the remote repository {}.",
                    last_validated_commit,
                    self.validation_auth_repo.name,
                )
                raise UpdateFailedError(
                    f"Commit {last_validated_commit} is no longer contained by repository"
                    f" {self.validation_auth_repo.name}. This could "
                    "either mean that there was an unauthorized push tot the remote "
                    "repository, or that last_validated_commit file was modified."
                )
            else:
                raise e

        # Check if the user's head commit matches the saved one
        # That should always be the case
        # If it is not, it means that someone, accidentally or maliciously made manual changes

        if not self.users_auth_repo.is_git_repository_root:
            users_head_sha = None
        elif settings.overwrite_last_validated_commit:
            users_head_sha = last_validated_commit
        else:
            if last_validated_commit is not None:
                users_head_sha = self.users_auth_repo.top_commit_of_branch("master")
            else:
                # if the user's repository exists, but there is no last_validated_commit
                # start the update from the beginning
                users_head_sha = None

        if last_validated_commit != users_head_sha:
            # TODO add a flag --force/f which, if provided, should force an automatic revert
            # of the users authentication repository to the last validated commit
            # This could be done if a user accidentally committed something to the auth repo
            # or manually pulled the changes
            # If the user deleted the repository or executed reset --hard, we could handle
            # that by starting validation from the last validated commit, as opposed to the
            # user's head sha.
            # For now, we will raise an error
            msg = (
                f"Saved last validated commit {last_validated_commit} does not match the head"
                f" commit of the authentication repository {users_head_sha}"
            )
            taf_logger.error(msg)
            raise UpdateFailedError(msg)

        # insert the current one at the beginning of the list
        if users_head_sha is not None:
            commits_since.insert(0, users_head_sha)

        self.commits = commits_since
        self.users_head_sha = users_head_sha
        self.current_commit_index = 0

    def _init_metadata(self):
        """
        TUF updater expects the existence of two directories in the client's
        metadata directory - current and previous. These directories store
        the current and previous metadata files (before and after the update).
        They must exists and contain at least root.json. Otherwise, update will
        fail. We actually want to validate the remote authentication repository,
        but will create the directories where TUF expects them to be in order
        to avoid modifying the updater.
        """
        # create current and previous directories and copy the metadata files
        # needed by the updater
        # TUF's updater expects these directories to be in the client's repository
        # read metadata of the cloned validation repo at the initial commit

        metadata_path = Path(self.repository_directory, "metadata")
        metadata_path.mkdir(parents=True, exist_ok=True)
        self.current_path = Path(metadata_path, "current")
        self.current_path.mkdir()
        self.previous_path = Path(metadata_path, "previous")
        self.previous_path.mkdir()

        metadata_files = self.validation_auth_repo.list_files_at_revision(
            self.current_commit, "metadata"
        )
        for filename in metadata_files:
            metadata = self.validation_auth_repo.get_file(
                self.current_commit, "metadata/" + filename
            )
            current_filename = self.current_path / filename
            previous_filename = self.previous_path / filename
            current_filename.write_text(metadata)
            shutil.copyfile(str(current_filename), str(previous_filename))

    def _clone_validation_repo(self, url):
        """
        Clones the authentication repository based on the url specified using the
        mirrors parameter. The repository is cloned as a bare repository
        to a the temp directory and will be deleted one the update is done.
        """
        temp_dir = tempfile.mkdtemp()
        path = Path(temp_dir, self.users_auth_repo.name).absolute()
        self.validation_auth_repo = GitRepository(path=path, repo_urls=[url])
        self.validation_auth_repo.clone(bare=True)
        self.validation_auth_repo.fetch(fetch_all=True)

    def cleanup(self):
        """
        Removes the bare authentication repository and current and previous
        directories. This should be called after the update is finished,
        either successfully or unsuccessfully.
        """
        if self.current_path.is_dir():
            shutil.rmtree(self.current_path)
        if self.previous_path.is_dir():
            shutil.rmtree(self.previous_path)
        temp_dir = Path(self.validation_auth_repo.path, os.pardir).parent
        shutil.rmtree(str(temp_dir), onerror=on_rm_error)

    def earliest_valid_expiration_time(self):
        # Only validate expiration time of the last commit
        if self.current_commit_index < len(self.commits) - 1:
            return 0
        return int(time.time())

    def ensure_not_changed(self, metadata_filename):
        """
        Make sure that the metadata file remained the same, as the reference metadata suggests.
        """
        current_file = self.get_metadata_file(
            self.current_commit, file_name=metadata_filename
        )
        previous_file = self.get_metadata_file(
            self.previous_commit, file_name=metadata_filename
        )
        if current_file.read() != previous_file.read():
            raise UpdateFailedError(
                f"Metadata file {metadata_filename} should be the same at revisions"
                f" {self.previous_commit} and {self.current_commit}, but is not."
            )

    def get_current_targets(self):
        return self.validation_auth_repo.list_files_at_revision(
            self.current_commit, "targets"
        )

    def get_mirrors(self, _file_type, _file_path):
        # pylint: disable=unused-argument
        # return a list containing just the current commit
        return [self.current_commit]

    def get_metadata_file(self, file_mirror, file_name, _upperbound_filelength=None):
        return self._get_file(file_mirror, "metadata/" + file_name)

    def get_target_file(self, file_mirror, _file_length, _download_safely, file_path):
        return self._get_file(file_mirror, "targets/" + file_path)

    def _get_file(self, commit, filepath):
        f = self.validation_auth_repo.get_file(commit, filepath)
        temp_file_object = securesystemslib.util.TempFile()
        temp_file_object.write(f.encode())
        return temp_file_object

    def get_file_digest(self, filepath, algorithm):
        filepath = Path(filepath).relative_to(self.validation_auth_repo.get_file)
        file_obj = self._get_file(self.current_commit, filepath)
        return securesystemslib.hash.digest_fileobject(file_obj, algorithm=algorithm)

    def on_successful_update(self, filename, mirror):
        # after the is successfully completed, set the
        # next commit as current for the given file
        taf_logger.debug("{} updated from commit {}", filename, mirror)

    def on_unsuccessful_update(self, filename):
        taf_logger.error("Failed to update {}", filename)

    def update_done(self):
        # the only metadata file that is always updated
        # regardless of if it changed or not is timestamp
        # so we can check if timestamp was updated a certain
        # number of times
        self.current_commit_index += 1
        return self.current_commit_index == len(self.commits)
