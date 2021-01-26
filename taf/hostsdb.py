import json
from pathlib import Path
from tuf.repository_tool import TARGETS_DIRECTORY_NAME
from taf.exceptions import GitError, InvalidOrMissingHostsError, RepositoryInstantiationError
from taf.log import taf_logger
from taf.auth_repo import NamedAuthenticationRepo
import taf.repositoriesdb as repositoriesdb

_hosts_db = {}


_repositories_dict = {}
_dependencies_dict = {}
DEPENDENCIES_JSON_PATH = f"{TARGETS_DIRECTORY_NAME}/dependencies.json"
MIRRORS_JSON_PATH = f"{TARGETS_DIRECTORY_NAME}/mirrors.json"
REPOSITORIES_JSON_PATH = f"{TARGETS_DIRECTORY_NAME}/repositories.json"
HOSTS_JSON_PATH = f"{TARGETS_DIRECTORY_NAME}/hosts.json"
AUTH_REPOS_HOSTS_KEY = "auth_repos"


def sort_repositories_by_host(root_repo, commit):

    repos_by_host = {}
    to_traverse = [root_repo]
    visited = []

    root_hosts = [_load_hosts_json(root_repo)]
    hosts_hierarchy_per_repo = {
        root_repo:  root_hosts
    }
    repositoriesdb.set_hosts_of_repo(root_repo, root_hosts)
    while len(to_traverse):
        auth_repo = to_traverse.pop()
        if auth_repo.name in visited:
            continue

        for host in auth_repo.hosts.keys():
            repos_by_host.setdefault(host, []).append(auth_repo)

        repositoriesdb.load_dependencies(auth_repo, commits=[commit], ancestor_hosts={commit: hosts_hierarchy_per_repo[auth_repo]})
        child_auth_repos = repositoriesdb.get_deduplicated_auth_repositories(auth_repo, commit)
        if len(child_auth_repos):
            for child_auth_repo in repositoriesdb.get_deduplicated_auth_repositories(auth_repo, commit):
                to_traverse.append(child_auth_repo)
                hosts_hierarchy_per_repo[child_auth_repo] = hosts_hierarchy_per_repo + [_load_hosts_json(child_auth_repo)]
    return repos_by_host





def _load_hosts_json(auth_repo, commit=None):
    if commit is None:
        commit = auth_repo.top_commit_of_branch("master")
    return _get_json_file(auth_repo, HOSTS_JSON_PATH, commit)


def _get_json_file(auth_repo, path, commit):
    try:
        return auth_repo.get_json(commit, path)
    except GitError:
        raise InvalidOrMissingHostsError(
            f"{path} not available at revision {commit}"
        )
    except json.decoder.JSONDecodeError:
        raise InvalidOrMissingHostsError(
            f"{path} not a valid json at revision {commit}"
        )