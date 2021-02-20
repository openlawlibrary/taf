import json
from pathlib import Path
from tuf.repository_tool import TARGETS_DIRECTORY_NAME
from taf.exceptions import (
    GitError,
    InvalidOrMissingHostsError,
    RepositoryInstantiationError,
)
from taf.log import taf_logger
from taf.auth_repo import NamedAuthenticationRepo
import taf.repositoriesdb as repositoriesdb

_hosts_dict = {}

DEPENDENCIES_JSON_PATH = f"{TARGETS_DIRECTORY_NAME}/dependencies.json"
MIRRORS_JSON_PATH = f"{TARGETS_DIRECTORY_NAME}/mirrors.json"
REPOSITORIES_JSON_PATH = f"{TARGETS_DIRECTORY_NAME}/repositories.json"
HOSTS_JSON_PATH = f"{TARGETS_DIRECTORY_NAME}/hosts.json"
AUTH_REPOS_HOSTS_KEY = "auth_repos"

class Host:

    def __init__(self, host):
        self.host = host
        self.auth_repos_with_custom = []

    def to_json(self):
        pass


def load_hosts(auth_repo, commits=None):
    """
    host_name: {
        commit: {
            loaded_repos: [auth_rpeo1, auth_repo2] - list repos that defined the host to avoid duplications
            "host": host object with auth repositories
        }
    }
    """

    global _hosts_dict
    if commits is None:
        commits = [auth_repo.top_commit_of_branch("master")]

    # can a host be defined in more than one repository?
    # if it is defined in multiple repositories, combine the data
    for commit in commits:
        hosts_data = _get_json_file(auth_repo, HOSTS_JSON_PATH, commit)
        for host_name, host_data in hosts_data.items():
            commits_hosts_dict = _hosts_dict.setdefault(host_name, {})
            if auth_repo.path in commits_hosts_dict.get("loaded_repos"):
                continue
            commits_hosts_dict.setdefault("loaded_repos", []).append(auth_repo.path)
            repositoriesdb.load_dependencies(
                auth_repo,
                root_dir=auth_repo.root_dir,
                commits=[commit],
            )
            child_repos = repositoriesdb.get_deduplicated_auth_repositories(auth_repo, [commit])
            host = commits_hosts_dict.get("host")
            if host is None:
                host = Host(host_name)
            commits_hosts_dict["host"]: host
            # if more than one authentication repository defines the same host
            # combine all all information about that host - each pair of auth repos and custom is added to a list
            auth_repos_info = {
                child_repo: host_data[AUTH_REPOS_HOSTS_KEY][child_repo.name] for child_repo in child_repos
                if child_repo.name in host_data[AUTH_REPOS_HOSTS_KEY]
            }
            host.auth_repos_with_custom.append({AUTH_REPOS_HOSTS_KEY: auth_repos_info, "custom": host_data.get("custom", {})})



def set_hosts_of_repo(auth_repo, hosts):
    hosts_of_repo = {}
    for hosts_info in hosts:
        for host, host_data in hosts_info.items():
            if not auth_repo.name in host_data[AUTH_REPOS_HOSTS_KEY]:
                continue
            data = dict(host_data)
            data.pop(AUTH_REPOS_HOSTS_KEY)
            hosts_of_repo[host] = data
    if not len(hosts_of_repo):
        taf_logger.warning(
            "Host of authentication repository {} not specified", auth_repo.name
        )
    auth_repo.hosts = hosts_of_repo


def load_hosts_json(auth_repo, commit=None):
    if commit is None:
        commit = auth_repo.top_commit_of_branch("master")
    return _get_json_file(auth_repo, HOSTS_JSON_PATH, commit)


def _get_json_file(auth_repo, path, commit):
    try:
        return auth_repo.get_json(commit, path)
    except GitError:
        raise InvalidOrMissingHostsError(f"{path} not available at revision {commit}")
    except json.decoder.JSONDecodeError:
        raise InvalidOrMissingHostsError(
            f"{path} not a valid json at revision {commit}"
        )
