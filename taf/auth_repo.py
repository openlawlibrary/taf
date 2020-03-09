import json
import os
import tempfile
from collections import defaultdict
from contextlib import contextmanager
from pathlib import Path
from tuf.repository_tool import METADATA_DIRECTORY_NAME
from taf.log import taf_logger
from taf.git import GitRepository, NamedGitRepository
from taf.repository_tool import (
    Repository as TAFRepository,
    get_role_metadata_path,
    get_target_path,
)


class AuthRepoMixin(TAFRepository):

    LAST_VALIDATED_FILENAME = "last_validated_commit"
    TEST_REPO_FLAG_FILE = "test-auth-repo"

    @property
    def conf_dir(self):
        """
        Returns location of the directory which stores the authentication repository's
        configuration files. That is, the last validated commit.
        Create the directory if it does not exist.
        """
        # the repository's name consists of the namespace and name (namespace/name)
        # the configuration directory should be _name
        last_dir = os.path.basename(os.path.normpath(self.path))
        conf_path = Path(self.path).parent / f"_{last_dir}"
        conf_path.mkdir(parents=True, exist_ok=True)
        return str(conf_path)

    @property
    def certs_dir(self):
        certs_dir = Path(self.path, "certs")
        certs_dir.mkdir(parents=True, exist_ok=True)
        return str(certs_dir)

    @property
    def last_validated_commit(self):
        """
        Return the last validated commit of the authentication repository
        """
        try:
            return Path(self.conf_dir, self.LAST_VALIDATED_FILENAME).read_text()
        except FileNotFoundError:
            return None

    def get_target(self, target_name, commit=None, safely=True):
        if commit is None:
            commit = self.head_commit_sha()
        target_path = get_target_path(target_name)
        if safely:
            return self.safely_get_json(commit, target_path)
        else:
            return self.get_json(commit, target_path)

    def is_commit_authenticated(self, target_name, commit):
        """Checks if passed commit is ever authenticated for given target name.
        """
        for auth_commit in self.all_commits_on_branch(reverse=False):
            target = self.get_target(target_name, auth_commit)
            try:
                if target["commit"] == commit:
                    return True
            except TypeError:
                continue
        return False

    @contextmanager
    def repository_at_revision(self, commit):
        """
        Context manager which makes sure that TUF repository is instantiated
        using metadata files at the specified revision. Creates a temp directory
        and metadata files inside it. Deleted the temp directory when no longer
        needed.
        """
        tuf_repository = self._tuf_repository
        with tempfile.TemporaryDirectory() as temp_dir:
            metadata_files = self.list_files_at_revision(
                commit, METADATA_DIRECTORY_NAME
            )
            Path(temp_dir, METADATA_DIRECTORY_NAME).mkdir(parents=True)
            for file_name in metadata_files:
                path = Path(temp_dir, METADATA_DIRECTORY_NAME, file_name)
                with open(path, "w") as f:
                    data = self.get_json(
                        commit, f"{METADATA_DIRECTORY_NAME}/{file_name}"
                    )
                    json.dump(data, f)
            self._load_tuf_repository(temp_dir)
            yield
            self._tuf_repository = tuf_repository

    def set_last_validated_commit(self, commit):
        """
        Set the last validated commit of the authentication repository
        """
        taf_logger.debug(
            "Auth repo {}: setting last validated commit to: {}", self.name, commit
        )
        Path(self.conf_dir, self.LAST_VALIDATED_FILENAME).write_text(commit)

    def sorted_commits_and_branches_per_repositories(self, commits):
        """Return a dictionary consisting of branches and commits belonging
        to it for every target repository:
        {
            target_repo1: {
                branch1: [commit1, commit2, commit3],
                branch2: [commit4, commit5]
            },
            target_repo2: {
                branch1: [commit6, commit7, commit8],
                branch2: [commit9, commit10]
            }
        }
        Keep in mind that targets metadata
        file is not updated everytime something is committed to the authentication repo.
        """
        repositories_commits = defaultdict(dict)
        targets = self.targets_at_revisions(*commits)
        previous_commits = {}
        for commit in commits:
            for target_path, target_data in targets[commit].items():
                target_branch = target_data.get("branch")
                target_commit = target_data.get("commit")
                previous_commit = previous_commits.get(target_path)
                if previous_commit is None or target_commit != previous_commit:
                    repositories_commits[target_path].setdefault(
                        target_branch, []
                    ).append(target_commit)
                previous_commits[target_path] = target_commit
        taf_logger.debug(
            "Auth repo {}: new commits per repositories according to targets.json: {}",
            self.name,
            repositories_commits,
        )
        return repositories_commits

    def targets_at_revisions(self, *commits):
        targets = defaultdict(dict)
        for commit in commits:
            # repositories.json might not exit, if the current commit is
            # the initial commit
            repositories_at_revision = self.safely_get_json(
                commit, get_target_path("repositories.json")
            )
            if repositories_at_revision is None:
                continue
            repositories_at_revision = repositories_at_revision["repositories"]

            # get names of all targets roles defined in the current revision
            with self.repository_at_revision(commit):
                roles_at_revision = self.get_all_targets_roles()

            for role_name in roles_at_revision:
                # targets metadata files corresponding to the found roles must exist
                targets_at_revision = self.get_json(
                    commit, get_role_metadata_path(role_name)
                )
                targets_at_revision = targets_at_revision["signed"]["targets"]

                for target_path in targets_at_revision:
                    if target_path not in repositories_at_revision:
                        # we only care about repositories
                        continue
                    try:
                        target_content = self.get_json(
                            commit, get_target_path(target_path)
                        )
                        target_commit = target_content.get("commit")
                        target_branch = target_content.get("branch", "master")
                        targets[commit][target_path] = {
                            "branch": target_branch,
                            "commit": target_commit,
                        }
                    except json.decoder.JSONDecodeError:
                        taf_logger.debug(
                            "Auth repo {}: target file {} is not a valid json at revision {}",
                            self.name,
                            target_path,
                            commit,
                        )
                        continue
        return targets


class AuthenticationRepo(GitRepository, AuthRepoMixin):
    def __init__(
        self,
        path,
        repo_urls=None,
        additional_info=None,
        default_branch="master",
        *args,
        **kwargs,
    ):
        super().__init__(path, repo_urls, additional_info, default_branch)


class NamedAuthenticationRepo(NamedGitRepository, AuthRepoMixin):
    def __init__(
        self,
        root_dir,
        repo_name,
        repo_urls=None,
        additional_info=None,
        default_branch="master",
        *args,
        **kwargs,
    ):
        super().__init__(
            root_dir=root_dir,
            repo_name=repo_name,
            repo_urls=repo_urls,
            additional_info=additional_info,
            default_branch=default_branch,
        )
