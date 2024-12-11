import json
import os
import tempfile
import fnmatch

from typing import Any, Callable, Dict, List, Optional, Union
from collections import defaultdict
from contextlib import contextmanager
from pathlib import Path
import pygit2
from tuf.repository_tool import METADATA_DIRECTORY_NAME
from taf.git import GitRepository
from taf.repository_tool import (
    Repository as TAFRepository,
    get_role_metadata_path,
    get_target_path,
)
from taf.constants import INFO_JSON_PATH


class AuthenticationRepository(GitRepository, TAFRepository):

    LAST_VALIDATED_FILENAME = "last_validated_commit"
    LAST_VALIDATED_KEY = "last_validated_commit"
    TEST_REPO_FLAG_FILE = "test-auth-repo"
    SCRIPTS_PATH = "scripts"

    _conf_dir = None
    _dependencies: Dict = {}

    def __init__(
        self,
        library_dir: Optional[Union[str, Path]] = None,
        name: Optional[str] = None,
        urls: Optional[List[str]] = None,
        custom: Optional[Dict] = None,
        default_branch: Optional[str] = None,
        allow_unsafe: Optional[bool] = False,
        conf_directory_root: Optional[str] = None,
        out_of_band_authentication: Optional[str] = None,
        path: Optional[Union[Path, str]] = None,
        alias: Optional[str] = None,
        *args,
        **kwargs,
    ):
        """
        Args:
          library_dir (Path or str): path to the library root. This is a directory which contains other repositories,
          whose full path is determined by appending their names to the library dir. A repository can be
          instantiated by specifying library dir and name, or by the full path.
          name (str): repository's name, which is appended to the library dir to form the full path.
          Must be in the namespace/name format. If library_dir is specified, name must be specified too.
          path (Path): repository's full filesystem path, which can be specified instead of name and library dir
          urls (list): repository's urls
          custom (dict): a dictionary containing other data
          default_branch (str): repository's default branch, automatically determined if not specified
          out_of_band_authentication (str): manually specified initial commit
          alias: Repository's alias, which will be used in logging statements to reference it
        """
        super().__init__(
            library_dir,
            name,
            urls,
            custom,
            default_branch,
            allow_unsafe,
            path,
            alias,
            *args,
            **kwargs,
        )

        if conf_directory_root is None:
            conf_directory_root_path = Path(self.path).parent
        else:
            conf_directory_root_path = Path(conf_directory_root)

        self.conf_directory_root = conf_directory_root_path.resolve()
        self.out_of_band_authentication = out_of_band_authentication

    # TODO rework conf_dir

    def to_json_dict(self) -> Dict:
        """Returns a dictionary mapping all attributes to their values"""
        data = super().to_json_dict()
        data.update(
            {
                "conf_directory_root": str(self.conf_directory_root),
                "out_of_band_authentication": self.out_of_band_authentication,
                "dependencies": self.dependencies,
            }
        )
        return data

    @property
    def conf_dir(self) -> str:
        """
        Returns location of the directory which stores the authentication repository's
        configuration files. That is, the last validated commit.
        Create the directory if it does not exist.
        """
        # the repository's name consists of the namespace and name (namespace/name)
        # the configuration directory should be _name
        if self._conf_dir is None:
            last_dir = os.path.basename(os.path.normpath(self.path))
            conf_path = self.conf_directory_root / f"_{last_dir}"
            conf_path.mkdir(parents=True, exist_ok=True)
            self._conf_dir = str(conf_path)
        return self._conf_dir

    @property
    def certs_dir(self) -> str:
        certs_dir = Path(self.path, "certs")
        return str(certs_dir)

    @property
    def dependencies(self) -> Dict:
        return self._dependencies

    @dependencies.setter
    def dependencies(self, value):
        self._dependencies = value

    @property
    def is_test_repo(self, branch: Optional[str] = None) -> bool:
        try:
            if branch is not None:
                commit = self.top_commit_of_branch(branch)
            else:
                commit = self.head_commit_sha()
            targets_data = self.get_metadata("targets", commit)
            if targets_data is None:
                return False
            return self.TEST_REPO_FLAG_FILE in targets_data["signed"]["targets"]
        except Exception as e:
            self._log_debug(f"Could not get targets.json metadata: {e}")
            return False

    @property
    def last_validated_commit(self) -> Optional[str]:
        """
        Last validated commit across the entire set of repositories, including authentication and target repositories.
        It is only validated if the update process does not skip any repository
        """
        try:
            if self.last_validated_data is not None:
                return self.last_validated_data[self.LAST_VALIDATED_KEY]
        except KeyError:
            return None
        return None

    @property
    def last_validated_data(self) -> Optional[dict]:
        """
        A dictionary containing the last validated commits for each repository, including both target repositories
        and the authentication repository. It also includes the last validated commit for when all repositories
        were simultaneously updated.
        """
        last_validated_data = {}
        last_validated_path = Path(self.conf_dir, self.LAST_VALIDATED_FILENAME)
        if last_validated_path.is_file():
            data = last_validated_path.read_text().strip()
            try:
                last_validated_data = json.loads(data)
            except json.decoder.JSONDecodeError:
                if data:
                    last_validated_data = {self.name: data}

        return last_validated_data

    @property
    def log_prefix(self) -> str:
        if self.alias:
            return f"{self.alias}: "
        return f"Auth repo {self.name}: "

    def commit_and_push(
        self,
        commit_msg: Optional[str] = None,
        push: Optional[bool] = True,
        commit: Optional[bool] = True,
    ) -> None:

        if commit:
            if commit_msg is None:
                commit_msg = input("\nEnter commit message and press ENTER\n\n")
            self.commit(commit_msg)

        if push:
            push_successful = self.push()
            if push_successful:
                new_commit_branch = self.default_branch
                if new_commit_branch:
                    new_commit = self.top_commit_of_branch(new_commit_branch)
                    if new_commit:
                        self.set_last_validated_of_repo(
                            self.name, new_commit, set_last_validated_commit=True
                        )
                        self._log_notice(
                            f"Updated last_validated_commit to {new_commit}"
                        )
                else:
                    self._log_warning(
                        "Default branch is None, skipping last_validated_commit update."
                    )

    def get_target(self, target_name, commit=None, safely=True) -> Optional[Dict]:
        if commit is None:
            commit = self.head_commit_sha()
        if commit is None:
            return None
        target_path = get_target_path(target_name)
        if safely:
            return self.safely_get_json(commit, target_path)
        else:
            return self.get_json(commit, target_path)

    def get_metadata(
        self, role: str, commit: Optional[str] = None, safely: bool = True
    ) -> Optional[Dict]:
        if commit is None:
            commit = self.head_commit_sha()
        if commit is None:
            return None
        metadata_path = get_role_metadata_path(role)
        if safely:
            return self.safely_get_json(commit, metadata_path)
        else:
            return self.get_json(commit, metadata_path)

    def get_info_json(
        self, commit: Optional[str] = None, safely: bool = True
    ) -> Optional[Dict]:
        head_commit = commit or self.head_commit_sha()
        if head_commit is None:
            return None
        if safely:
            return self.safely_get_json(head_commit, INFO_JSON_PATH)
        else:
            return self.get_json(head_commit, INFO_JSON_PATH)

    def get_metadata_path(self, role):
        return self.path / METADATA_DIRECTORY_NAME / f"{role}.json"

    def is_commit_authenticated(self, target_name: str, commit: str) -> bool:
        """Checks if passed commit is ever authenticated for given target name."""
        for auth_commit in self.all_commits_on_branch(reverse=False):
            target = self.get_target(target_name, auth_commit)
            if target is None:
                continue
            try:
                if target["commit"] == commit:
                    return True
            except TypeError:
                continue
        return False

    @contextmanager
    def repository_at_revision(self, commit: str):
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

    def set_last_validated_data(
        self,
        last_validated_data: dict,
        set_last_validated_commit: Optional[bool] = True,
    ):
        """
        Set the last validated data of the authentication repository.
        In case of a partial update (update run with the --exclude-target option),
        update last validated commits of target repositories that were updated
        """
        if set_last_validated_commit:
            last_validated_data[self.LAST_VALIDATED_KEY] = last_validated_data[
                self.name
            ]
        last_data_str = json.dumps(last_validated_data, indent=4)
        self._log_debug(f"setting last validated data to: {last_data_str}")
        Path(self.conf_dir, self.LAST_VALIDATED_FILENAME).write_text(last_data_str)

    def set_last_validated_of_repo(
        self,
        repo_name: str,
        commit: str,
        set_last_validated_commit: Optional[bool] = True,
    ):
        last_validated_data = self.last_validated_data or {}
        last_validated_data[repo_name] = commit
        last_validated_data[self.LAST_VALIDATED_KEY] = commit
        last_data_str = json.dumps(last_validated_data, indent=4)
        self._log_debug(f"setting last validated data to: {last_data_str}")
        if set_last_validated_commit and self.name == repo_name:
            last_validated_data[self.LAST_VALIDATED_KEY] = last_validated_data[
                self.name
            ]
        Path(self.conf_dir, self.LAST_VALIDATED_FILENAME).write_text(last_data_str)

    def auth_repo_commits_after_repos_last_validated(
        self, target_repos: List, last_validated_data
    ) -> List[str]:
        """
        Traverses the commit history from the most recent commit back to the oldest last validated commit
        of the target repositories. It then quantifies how many of these commits are related to each target repository.

        Returns:
            tuple:
                - List[str]: A list of commit hashes from the oldest last validated commit to the newest commit
                in the authentication repository. This list provides a sequential history of commits affecting
                the target repositories.
        """
        last_validated_target_commits = defaultdict(list)
        for repo in target_repos:
            last_validated_commit = last_validated_data[repo.name]
            last_validated_target_commits[last_validated_commit].append(repo)

        repo = self.pygit_repo

        walker = repo.walk(repo.head.target, pygit2.GIT_SORT_TOPOLOGICAL)

        traversed_commits = []
        for commit in walker:
            commit_id = str(commit.id)
            if commit_id in last_validated_target_commits:
                last_validated_target_commits.pop(commit_id)

            traversed_commits.append(commit_id)
            if not len(last_validated_target_commits):
                break
        traversed_commits.reverse()
        return traversed_commits

    def targets_data_by_auth_commits(
        self,
        commits: List[str],
        target_repos: Optional[List[str]] = None,
        custom_fns: Optional[Dict[str, Callable]] = None,
        default_branch: Optional[str] = None,
        excluded_target_globs: Optional[List[str]] = None,
        last_commits_per_repos: Optional[Dict[str, List]] = None,
    ) -> Dict[str, Dict[str, Dict[str, Any]]]:
        """
        Return a dictionary where each target repository has associated authentication commits,
        and for each authentication commit, there's a dictionary of the branch, commit and custom data.

        {
            'target_repo1': {
                'auth_commit1': {'branch': 'branch1', 'commit': 'commit1', 'custom': {}},
                'auth_commit2': {'branch': 'branch1', 'commit': 'commit2', 'custom': {}},
                ...
            },
            'target_repo2': {
                ...
            },
            ...
        }

        """
        repositories_commits: Dict[str, Dict[str, Dict[str, Any]]] = {}
        targets = self.targets_at_revisions(
            commits,
            target_repos=target_repos,
            default_branch=default_branch,
            last_commits_per_repos=last_commits_per_repos,
        )
        excluded_target_globs = excluded_target_globs or []
        for commit in commits:
            for target_path, target_data in targets[commit].items():
                if any(
                    fnmatch.fnmatch(target_path, excluded_target_glob)
                    for excluded_target_glob in excluded_target_globs
                ):
                    continue

                target_branch = target_data.get("branch")
                target_commit = target_data.get("commit")
                target_data.setdefault("custom", {})
                if custom_fns is not None and target_path in custom_fns:
                    target_data["custom"].update(custom_fns[target_path](target_commit))

                repositories_commits.setdefault(target_path, {})[commit] = {
                    "branch": target_branch,
                    "commit": target_commit,
                    "custom": target_data.get("custom"),
                }

        self._log_debug(
            f"new commits per repositories according to target files: {repositories_commits}"
        )
        return repositories_commits

    def sorted_commits_and_branches_per_repositories(
        self,
        commits: List[str],
        target_repos: Optional[List[str]] = None,
        custom_fns: Optional[Dict[str, Callable]] = None,
        default_branch: Optional[str] = None,
        excluded_target_globs: Optional[List[str]] = None,
    ) -> Dict[str, Dict[str, List[Dict[str, Any]]]]:
        """Return a dictionary consisting of branches and commits belonging
        to it for every target repository:
        {
            target_repo1: {
                branch1: [
                    {"commit": commit1, "custom": {...}, "auth_commit": auth_commit1},
                    {"commit": commit2, "custom": {...}, "auth_commit": auth_commit2},
                    {"commit": commit3, "custom": {...}, "auth_commit": auth_commit3}
                ],
                branch2: [
                    {"commit": commit4, "custom": {...}, "auth_commit": auth_commit4},
                    {"commit": commit5, "custom": {...}, "auth_commit": auth_commit5}
                ]
            },
            target_repo2: {
                branch1: [
                    {"commit": commit6, "custom": {...}, "auth_commit": auth_commit6}
                ],
                branch2: [
                    {"commit": commit7, "custom": {...}, "auth_commit": auth_commit7}
                ]
            }
        }
        Keep in mind that targets metadata
        file is not updated everytime something is committed to the authentication repo.
        """
        repositories_commits: Dict = defaultdict(dict)
        targets = self.targets_at_revisions(
            commits, target_repos=target_repos, default_branch=default_branch
        )
        previous_commits: Dict = {}
        skipped_targets = []
        excluded_target_globs = excluded_target_globs or []
        for commit in commits:
            for target_path, target_data in targets[commit].items():
                if target_path in skipped_targets:
                    continue
                if any(
                    fnmatch.fnmatch(target_path, excluded_target_glob)
                    for excluded_target_glob in excluded_target_globs
                ):
                    skipped_targets.append(target_path)
                    continue
                target_branch = target_data.get("branch")
                target_commit = target_data.get("commit")
                previous_data = previous_commits.get(target_path)
                target_data.setdefault("custom", {})
                if (
                    previous_data is None
                    or (target_commit, target_branch) != previous_data
                ):
                    if custom_fns is not None and target_path in custom_fns:
                        target_data["custom"].update(
                            custom_fns[target_path](target_commit)
                        )

                    repositories_commits[target_path].setdefault(
                        target_branch, []
                    ).append(
                        {
                            "commit": target_commit,
                            "custom": target_data.get("custom"),
                            "auth_commit": commit,
                        }
                    )
                previous_commits[target_path] = (target_commit, target_branch)
        self._log_debug(
            f"new commits per repositories according to target files: {repositories_commits}"
        )
        return repositories_commits

    def targets_at_revisions(
        self,
        commits,
        target_repos=None,
        default_branch=None,
        last_commits_per_repos=None,
    ):
        targets = defaultdict(dict)
        if default_branch is None:
            default_branch = self.default_branch
        previous_metadata = []
        new_files = []
        repos_to_skip = []
        for commit in reversed(commits):
            # repositories.json might not exit, if the current commit is
            # the initial commit
            repositories_at_revision = self.safely_get_json(
                commit, get_target_path("repositories.json")
            )
            if repositories_at_revision is None:
                continue
            repositories_at_revision = repositories_at_revision["repositories"]

            current_metadata = self.list_files_at_revision(
                commit, METADATA_DIRECTORY_NAME
            )
            new_files = [
                metadata_path
                for metadata_path in current_metadata
                if metadata_path not in previous_metadata
            ]
            previous_metadata = current_metadata
            if len(new_files):
                with self.repository_at_revision(commit):
                    roles_at_revision = self.get_all_targets_roles()

            for role_name in roles_at_revision:
                # targets metadata files corresponding to the found roles must exist
                targets_at_revision = self.safely_get_json(
                    commit, get_role_metadata_path(role_name)
                )
                if targets_at_revision is None:
                    continue
                targets_at_revision = targets_at_revision["signed"]["targets"]

                for target_path in targets_at_revision:
                    # if there are older auth repo commits corresponding to repositories
                    # that were not validated in the one or more previous updates
                    # skip the ones that were validated more recently
                    # when the last validated commit of a repo is reached
                    # the repo is added to the repos_to_skip list
                    if target_path in repos_to_skip:
                        continue
                    if (
                        last_commits_per_repos
                        and last_commits_per_repos.get(target_path) == commit
                    ):
                        repos_to_skip.append(target_path)
                    if target_path not in repositories_at_revision:
                        # we only care about repositories
                        continue
                    if target_repos and target_path not in target_repos:
                        # if specific target repositories are specified, skip all other
                        # repositories
                        continue
                    target_content = self.safely_get_json(
                        commit, get_target_path(target_path)
                    )
                    if target_content is not None:
                        target_commit = target_content.pop("commit")
                        target_branch = target_content.pop("branch", default_branch)
                        targets[commit][target_path] = {
                            "branch": target_branch,
                            "commit": target_commit,
                            "custom": target_content,
                        }
        return targets
