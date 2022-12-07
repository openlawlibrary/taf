import os
import shutil
import tempfile
from functools import wraps
from pathlib import Path

from tuf.ngclient._internal import trusted_metadata_set
from taf.exceptions import GitError
from taf.log import taf_logger
import taf.settings as settings
from taf.auth_repo import AuthenticationRepository
from taf.exceptions import UpdateFailedError
from taf.utils import on_rm_error
from taf.updater.git_trusted_metadata_set import GitTrustedMetadataSet

from tuf.ngclient.fetcher import FetcherInterface
from tuf.api.exceptions import DownloadHTTPError


class GitUpdater(FetcherInterface):
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
    - A commit is considered to be a TUF Updater instance. We keep track of the current commit.
    - This class is designed in such a way that for each subsequent call of the
    updater's refresh method the metadata from next commit is used within TUF's updater.
    - The updater's method for downloading and retrieving current metadata is overriden
    by our own '_fetch' call. We override TUF's FetcherInterface abstract class to fetch
    metadata from local git revisions, instead of by downloading data from another protocol,
    like http/https. So, what we want to do is to return the current commit,
    and just the current commit. This means that that an exception will be raised
    if the version of the metadata file at that commit is not valid.
    - The same logic is used to handle targets.


    Attributes:
        - repository_directory: the client's local repository's location
        - metadata_dir_path: path of the metadata directory needed by the updater.
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

    @property
    def metadata_dir(self):
        return str(self.metadata_dir_path)

    @property
    def targets_dir(self):
        return str(self.validation_auth_repo.path / "targets")

    def __init__(self, auth_url, repository_directory, repository_name):
        """
        Args:
        auth_url: repository url of the git repository which we want to clone.
        repository_directory: the client's local repository's location
        repository_name: name of the repository in 'organization/namespace' format.
        """
        self._original_tuf_trusted_metadata_set = (
            trusted_metadata_set.TrustedMetadataSet
        )
        self._patch_tuf_metadata_set(GitTrustedMetadataSet)

        conf_directory_root = settings.conf_directory_root
        default_branch = settings.default_branch
        validation_path = settings.validation_repo_path

        self.set_validation_repo(validation_path, auth_url)

        # users_auth_repo is the authentication repository
        # located on the users machine which needs to be updated
        self.users_auth_repo = AuthenticationRepository(
            repository_directory,
            repository_name,
            default_branch=default_branch,
            urls=[auth_url],
            conf_directory_root=conf_directory_root,
        )

        repository_directory = Path(self.users_auth_repo.path)

        if repository_directory.exists():
            if not self.users_auth_repo.is_git_repository_root:
                if len(list(repository_directory.glob("*"))):
                    raise UpdateFailedError(
                        f"{repository_directory} is not a git repository and is not empty"
                    )

        self._init_commits()

        self.repository_directory = str(repository_directory)

        tmp_dir = tempfile.mkdtemp()
        metadata_path = Path(tmp_dir, "metadata")
        metadata_path.mkdir(parents=True, exist_ok=True)

        self.metadata_dir_path = metadata_path

        try:
            self._init_metadata()
        except Exception:
            self.cleanup()
            raise UpdateFailedError(
                "Could not load metadata. Check if the URL and filesystem paths are correct."
            )

    def _fetch(self, url):
        try:
            return [
                self.validation_auth_repo.get_file(self.current_commit, url, raw=True)
            ]
        except GitError:
            raise DownloadHTTPError(f"Could not find {url}", status_code=404)
        except Exception as e:
            taf_logger.error(
                f"Retrieval of data at current revision {self.current_commit} failed with error - {str(e)}"
            )
            raise e

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
            if "Invalid revision range" in str(e):
                taf_logger.error(
                    "Commit {} is not contained by the remote repository {}.",
                    last_validated_commit,
                    self.validation_auth_repo.name,
                )
                raise UpdateFailedError(
                    f"Commit {last_validated_commit} is no longer contained by repository"
                    f" {self.validation_auth_repo.name}. This could "
                    "either mean that there was an unauthorized push to the remote "
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
                users_head_sha = self.users_auth_repo.top_commit_of_branch(
                    self.users_auth_repo.default_branch
                )
            else:
                # if the user's repository exists, but there is no last_validated_commit
                # start the update from the beginning
                users_head_sha = None

        if last_validated_commit != users_head_sha:
            # if a user committed something to the repo or manually pulled the changes
            # last_validated_commit will no longer match the top commit, but the repository
            # might still be completely valid
            # committing without pushing is not valid
            # user_head_sha should be newer than last validated commit
            if users_head_sha not in commits_since:
                msg = f"Top commit of repository {self.users_auth_repo.name} {users_head_sha} and is not equal to or newer than last successful commit"
                taf_logger.error(msg)
                raise UpdateFailedError(msg)
            users_head_sha = last_validated_commit

        # insert the current one at the beginning of the list
        if users_head_sha is not None:
            commits_since.insert(0, users_head_sha)

        self.commits = commits_since
        self.users_head_sha = users_head_sha
        self.current_commit_index = 0

    def _init_metadata(self):
        """
        TUF updater expects the existence of a client
        metadata directory. This directory stores
        the current metadata files (which will get deleted after the update).
        Directory must exist and contain at least root.json. Otherwise, update will
        fail. We actually want to validate the remote authentication repository,
        but will create a Temp directory in order to avoid modifying the updater.
        """
        metadata_files = self.validation_auth_repo.list_files_at_revision(
            self.current_commit, "metadata"
        )
        for filename in metadata_files:
            metadata = self.validation_auth_repo.get_file(
                self.current_commit, "metadata/" + filename
            )
            current_filename = self.metadata_dir_path / filename
            current_filename.write_text(metadata)

    def _patch_tuf_metadata_set(self, cls):
        """
        Used to address TUF metadata expiration.
        We skip validating expiration for metadata in older commits and
        revert-back to TUF metadata validation on the latest commit"""
        trusted_metadata_set.TrustedMetadataSet = cls

    def revert_tuf_patch_on_last_commit(f):
        """
        We only want to validate metadata expiration date for most recent commit.
        Since we turned off metadata validation for all commits, we want to revert this patch for the most recent commit.
        This decorator reverts our metadata expiration patch to original TUF implementation.
        """
        wraps(f)

        def wrapper(self):
            if self.current_commit_index + 1 == (len(self.commits) - 1):
                self._patch_tuf_metadata_set(self._original_tuf_trusted_metadata_set)
            return f(self)

        return wrapper

    def set_validation_repo(self, path, url):
        """
        Used outside of GitUpdater to access validation auth repo.
        """
        self.validation_auth_repo = AuthenticationRepository(path=path, urls=[url])

    def cleanup(self):
        """
        Removes the bare authentication repository and metadata
        directory. This should be called after the update is finished,
        either successfully or unsuccessfully.
        """
        if self.metadata_dir_path.is_dir():
            shutil.rmtree(self.metadata_dir_path)
        self.validation_auth_repo.cleanup()
        temp_dir = Path(self.validation_auth_repo.path, os.pardir).parent
        if temp_dir.is_dir():
            shutil.rmtree(str(temp_dir), onerror=on_rm_error)

    def get_current_targets(self):
        try:
            return self.validation_auth_repo.list_files_at_revision(
                self.current_commit, "targets"
            )
        except GitError:
            return []

    def get_current_target_data(self, filepath, raw=False):
        return self.validation_auth_repo.get_file(
            self.current_commit, f"targets/{filepath}", raw=raw
        )

    @revert_tuf_patch_on_last_commit
    def update_done(self):
        """Used to indicate whether updater has finished with update.
        Update is considered done when all commits have been validated"""
        self.current_commit_index += 1
        return self.current_commit_index == len(self.commits)
