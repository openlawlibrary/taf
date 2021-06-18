import json
import os
import tempfile
from collections import defaultdict
from contextlib import contextmanager
from pathlib import Path
from tuf.repository_tool import METADATA_DIRECTORY_NAME
from taf.git import GitRepository
from taf.repository_tool import (
    Repository as TAFRepository,
    get_role_metadata_path,
    get_target_path,
)


class AuthenticationRepository(GitRepository, TAFRepository):

    LAST_VALIDATED_FILENAME = "last_validated_commit"
    TEST_REPO_FLAG_FILE = "test-auth-repo"
    HOSTS_FILE = "hosts.json"
    SCRIPTS_PATH = "scripts"
    AUTH_REPOS_HOSTS_KEY = "auth_repos"

    _conf_dir = None

    def __init__(
        self,
        library_dir=None,
        name=None,
        urls=None,
        custom=None,
        default_branch="main",
        conf_directory_root=None,
        out_of_band_authentication=None,
        hosts=None,
        path=None,
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
          default_branch (str): repository's default branch ("main" if not defined)
          out_of_band_authentication (str): manually specified initial commit
          hosts (dict): host data is specified using the hosts.json file. Hosts of the current repo
          can be specified in its parent's repo (meaning that this repo is listed in the parent's dependencies.json),
          or it can be specified in hosts.json contained by the repo itself. If hosts data is defined in the parent,
          it can be propagated to the contained repos. `load_hosts` function of the `hosts` module sets this
          attribute.
        """
        super().__init__(
            library_dir, name, urls, custom, default_branch, path, *args, **kwargs
        )

        if conf_directory_root is None:
            conf_directory_root = Path(self.path).parent
        self.conf_directory_root = Path(conf_directory_root).resolve()
        self.out_of_band_authentication = out_of_band_authentication
        # host data can be specified in the current authentication repository or in its parent
        # the input parameter hosts is expected to contain hosts data specified outside of
        # this repository's hosts file specifying its hosts
        # in other words, propagate hosts data from parent to the child repository
        self.hosts = hosts

    # TODO rework conf_dir

    def to_json_dict(self):
        """Returns a dictionary mapping all attributes to their values"""
        data = super().to_json_dict()
        data.update(
            {
                "conf_directory_root": str(self.conf_directory_root),
                "out_of_band_authentication": self.out_of_band_authentication,
                "hosts": self.hosts,
            }
        )
        return data

    @property
    def conf_dir(self):
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
    def certs_dir(self):
        certs_dir = Path(self.path, "certs")
        certs_dir.mkdir(parents=True, exist_ok=True)
        return str(certs_dir)

    @property
    def is_test_repo(self):
        return Path(self.path, self.targets_path, self.TEST_REPO_FLAG_FILE).is_file()

    @property
    def last_validated_commit(self):
        """
        Return the last validated commit of the authentication repository
        """
        try:
            return Path(self.conf_dir, self.LAST_VALIDATED_FILENAME).read_text()
        except FileNotFoundError:
            return None

    _hosts_conf = None

    @property
    def hosts_conf(self):
        if self._hosts_conf is None:
            self._hosts_conf = self.get_target(self.HOSTS_FILE)
        return self._hosts_conf

    @property
    def log_prefix(self):
        return f"Auth repo {self.name}: "

    def get_target(self, target_name, commit=None, safely=True):
        if commit is None:
            commit = self.head_commit_sha()
        target_path = get_target_path(target_name)
        if safely:
            return self.safely_get_json(commit, target_path)
        else:
            return self.get_json(commit, target_path)

    def is_commit_authenticated(self, target_name, commit):
        """Checks if passed commit is ever authenticated for given target name."""
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
        self._log_debug(f"setting last validated commit to: {commit}")
        Path(self.conf_dir, self.LAST_VALIDATED_FILENAME).write_text(commit)

    def sorted_commits_and_branches_per_repositories(
        self, commits, target_repos=None, custom_fns=None
    ):
        """Return a dictionary consisting of branches and commits belonging
        to it for every target repository:
        {
            target_repo1: {
                branch1: [{"commit": commit1, "custom": {...}}, {"commit": commit2, "custom": {...}}, {"commit": commit3, "custom": {}}],
                branch2: [{"commit": commit4, "custom: {...}}, {"commit": commit5, "custom": {}}]
            },
            target_repo2: {
                branch1: [{"commit": commit6, "custom": {...}}],
                branch2: [{"commit": commit7", "custom": {...}]
            }
        }
        Keep in mind that targets metadata
        file is not updated everytime something is committed to the authentication repo.
        """
        repositories_commits = defaultdict(dict)
        targets = self.targets_at_revisions(*commits, target_repos=target_repos)
        previous_commits = {}
        for commit in commits:
            for target_path, target_data in targets[commit].items():
                target_branch = target_data.get("branch")
                target_commit = target_data.get("commit")
                previous_commit = previous_commits.get(target_path)
                target_data.setdefault("custom", {})

                if previous_commit is None or target_commit != previous_commit:
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
                        }
                    )
                previous_commits[target_path] = target_commit
        self._log_debug(
            f"new commits per repositories according to target files: {repositories_commits}"
        )
        return repositories_commits

    def targets_at_revisions(self, *commits, target_repos=None):
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
                    if target_repos is not None and target_path not in target_repos:
                        # if specific target repositories are specified, skip all other
                        # repositories
                        continue
                    target_content = self.safely_get_json(
                        commit, get_target_path(target_path)
                    )
                    if target_content is not None:
                        target_commit = target_content.pop("commit")
                        target_branch = target_content.pop("branch", "master")
                        targets[commit][target_path] = {
                            "branch": target_branch,
                            "commit": target_commit,
                            "custom": target_content,
                        }
        return targets
