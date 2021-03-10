import glob
import json
import os
import tempfile
from collections import defaultdict
from contextlib import contextmanager
from pathlib import Path
from tuf.repository_tool import METADATA_DIRECTORY_NAME
from taf.git import GitRepository, NamedGitRepository
from taf.repository_tool import (
    Repository as TAFRepository,
    get_role_metadata_path,
    get_target_path,
)


class AuthRepoMixin(TAFRepository):

    LAST_VALIDATED_FILENAME = "last_validated_commit"
    LAST_SUCCESSFUL_COMMITS = "last_successful_commits.json"
    TEST_REPO_FLAG_FILE = "test-auth-repo"
    HOSTS_FILE = "hosts.json"
    SCRIPTS_PATH = "scripts"
    AUTH_REPOS_HOSTS_KEY = "auth_repos"

    _conf_dir = None

    def __init__(
        self, conf_directory_root, out_of_band_authentication=None, hosts=None
    ):
        if conf_directory_root is None:
            conf_directory_root = str(Path(self.path).parent)
        self.conf_directory_root = conf_directory_root
        self.out_of_band_authentication = out_of_band_authentication
        # host data can be specified in the current authentication repository or in its parent
        # the input parameter hosts is expected to contain hosts date specified outside of
        # this repository's hosts file specifying its hosts
        self.hosts = hosts

    # TODO rework conf_dir

    @classmethod
    def from_json_dict(cls, json_data):
        path = json_data.pop("path")
        urls = json_data.pop("urls")
        custom = json_data.pop("custom", None)
        name = json_data.pop("name")
        default_branch = json_data.pop("default_branch", "master")
        return cls(path, urls, custom, default_branch, name, **json_data)

    def to_json_dict(self):
        return {
            "path": str(self.path),
            "urls": self.urls,
            "name": self.name,
            "default_branch": self.default_branch,
            "custom": self.custom,
        }

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
            conf_path = Path(self.conf_directory_root, f"_{last_dir}")
            conf_path.mkdir(parents=True, exist_ok=True)
            self._conf_dir = str(conf_path)
        return self._conf_dir

    @property
    def certs_dir(self):
        certs_dir = Path(self.path, "certs")
        certs_dir.mkdir(parents=True, exist_ok=True)
        return str(certs_dir)

    def get_hosts_of_repo(self, repo):
        repo_hosts = {}
        for host, host_data in self.hosts_conf.items():
            repos = host_data.get(self.AUTH_REPOS_HOSTS_KEY)
            for repo_name in repos:
                if repo_name == repo.name:
                    repo_hosts[host] = dict(host_data)
                    repo_hosts[host].remove(self.AUTH_REPO_HOSTS_KEY)
                    break
        return repo_hosts

    @property
    def last_validated_commit(self):
        """
        Return the last validated commit of the authentication repository
        """
        try:
            return Path(self.conf_dir, self.LAST_VALIDATED_FILENAME).read_text()
        except FileNotFoundError:
            return None

    @property
    def last_successful_commits(self):
        """
        A file containing last commits successfully handled by scripts
        """
        path = os.path.join(self.conf_dir, self.LAST_SUCCESSFUL_COMMITS)
        try:
            with open(path) as f:
                return json.load(f)
        except (FileNotFoundError, json.decoder.JSONDecodeError):
            return {}

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

    def execute_scirpts(self):
        scripts_path = Path(self.path, self.get_target_path(self.SCRIPTS_PATH))
        scripts = glob.glob(f"{scripts_path}/*.py")
        scripts = [script for script in scripts.sort() if script[0].isdigit()]

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

    def set_last_successful_commits(self, action, env_data):
        last_successful_commits = self.last_successful_commits
        for env, data in env_data.items():
            last_successful_commits.setdefault(env, {})
            if isinstance(data, dict):
                for key, value in data.items():
                    last_successful_commits[env].setdefault(action, {})[key] = value
            else:
                last_successful_commits[env][action] = data

        self._log_debug(
            f"setting last successfult commits to:\n{last_successful_commits}"
        )
        (Path(self.conf_dir) / "last_successful_commits.json").write_text(
            json.dumps(last_successful_commits, indent=4)
        )

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


class AuthenticationRepo(GitRepository, AuthRepoMixin):
    def __init__(
        self,
        path,
        urls=None,
        custom=None,
        default_branch="master",
        conf_directory_root=None,
        name=None,
        out_of_band_authentication=None,
        hosts=None,
        *args,
        **kwargs,
    ):
        GitRepository.__init__(
            self,
            path,
            urls=urls,
            custom=custom,
            default_branch=default_branch,
            name=name,
        )
        AuthRepoMixin.__init__(
            self,
            conf_directory_root=conf_directory_root,
            out_of_band_authentication=out_of_band_authentication,
            hosts=hosts,
        )

    @classmethod
    def from_json_dict(cls, json_data):
        path = json_data.pop("path")
        urls = json_data.pop("urls")
        custom = json_data.pop("custom")
        name = json_data.pop("name")
        default_branch = json_data.pop("default_branch")
        hosts = json_data.pop("hosts", None)
        conf_directory_root = json_data.pop("root_dir", None)
        out_of_band_authentication = json_data.pop("out_of_banch_authentication", None)
        return cls(
            path, urls, custom, default_branch, conf_directory_root,
            name, out_of_band_authentication, hosts, **json_data
        )

    def to_json(self):
        return json.dumps(
            {
                "path": str(self.path),
                "name": self.name,
                "urls": self.urls,
                "custom": self.custom,
                "default_branch": self.default_branch,
                "hosts": self.hosts,
                "out_of_band_authentication": self.out_of_band_authentication
            }
        )


class NamedAuthenticationRepo(NamedGitRepository, AuthRepoMixin):
    def __init__(
        self,
        root_dir,
        name,
        urls=None,
        out_of_band_authentication=None,
        custom=None,
        default_branch="master",
        conf_directory_root=None,
        hosts=None,
        *args,
        **kwargs,
    ):
        NamedGitRepository.__init__(
            self,
            root_dir=root_dir,
            name=name,
            urls=urls,
            custom=custom,
            default_branch=default_branch,
            *args,
            **kwargs
        )
        AuthRepoMixin.__init__(
            self,
            conf_directory_root=conf_directory_root,
            out_of_band_authentication=out_of_band_authentication,
            hosts=hosts,
        )

    @classmethod
    def from_json_dict(cls, json_data):
        json_data.pop("path", None)
        root_dir = json_data.pop("root_dir")
        urls = json_data.pop("urls")
        custom = json_data.pop("custom", None)
        name = json_data.pop("name")
        default_branch = json_data.pop("default_branch", "master")
        hosts = json_data.pop("hosts", None)
        conf_directory_root = json_data.pop("root_dir", None)
        out_of_band_authentication = json_data.pop("out_of_band_authentication", None)
        return cls(
            root_dir,
            name,
            urls=urls,
            out_of_band_authentication=out_of_band_authentication,
            custom=custom,
            default_branch=default_branch,
            conf_directory_root=conf_directory_root,
            hosts=hosts,
            **json_data,
        )

    def to_json_dict(self):
        return {
            "root_dir": str(self.root_dir),
            "name": self.name,
            "path": self.path,
            "urls": self.urls,
            "custom": self.custom,
            "default_branch": self.default_branch,
            "out_of_band_authentication": self.out_of_band_authentication,
            "hosts": self.hosts,
        }
