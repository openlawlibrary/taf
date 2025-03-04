import os
import shutil
import tempfile
from functools import wraps
from pathlib import Path

from taf.models.types import Commitish
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
    - The updater's method for downloading and retrieving current metadata is overridden
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
        - commits: a list of commits, starting with the most recent commit in the
        user's repository. The following commits are those committed after the
        the top one if the client's repo.
        - commits_indexes: a dictionary which stores index of the current commit
        per metadata file. The reason for separating the metadata files is that
        not all files are updated at the same time.
    """

    @property
    def current_commit(self) -> Commitish:
        return self.commits[self.current_commit_index]

    @property
    def previous_commit(self) -> Commitish:
        return self.commits[self.current_commit_index - 1]

    @property
    def metadata_dir(self) -> str:
        return str(self.metadata_dir_path)

    @property
    def targets_dir(self) -> str:
        return str(self.validation_auth_repo.path / "targets")

    def __init__(self, auth_urls, repository_directory, repository_name):
        """
        Args:
        auth_url: repository url of the git repository which we want to clone.
        repository_directory: the client's local repository's location
        repository_name: name of the repository in 'organization/namespace' format.
        """
        self.repository_name = repository_name
        self._original_tuf_trusted_metadata_set = (
            trusted_metadata_set.TrustedMetadataSet
        )
        self._patch_tuf_metadata_set(GitTrustedMetadataSet)

        validation_path = settings.validation_repo_path.get(repository_name)

        self.set_validation_repo(validation_path, auth_urls)

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
        last_validated_commit = Commitish.from_hash(
            settings.last_validated_commit.get(self.repository_name)
        )

        commits_since = self.validation_auth_repo.all_commits_since_commit(
            last_validated_commit
        )

        # insert the current one at the beginning of the list
        if last_validated_commit is not None:
            commits_since.insert(0, last_validated_commit)

        self.commits = commits_since
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

    def set_validation_repo(self, path, urls):
        """
        Used outside of GitUpdater to access validation auth repo.
        """
        self.validation_auth_repo = AuthenticationRepository(path=path, urls=urls)

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

    def get_current_metadata(self):
        try:
            return self.validation_auth_repo.list_files_at_revision(
                self.current_commit, "metadata"
            )
        except GitError:
            return []

    def get_current_target_data(self, filepath, raw=False):
        return self.validation_auth_repo.get_file(
            self.current_commit, f"targets/{filepath}", raw=raw
        )

    def get_current_metadata_data(self, filepath, raw=False):
        return self.validation_auth_repo.get_file(
            self.current_commit, f"metadata/{filepath}", raw=raw
        )

    @revert_tuf_patch_on_last_commit  # type: ignore
    def update_done(self):
        """Used to indicate whether updater has finished with update.
        Update is considered done when all commits have been validated"""
        self.current_commit_index += 1
        return self.current_commit_index == len(self.commits)
