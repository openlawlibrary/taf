import json
from tuf.repository_tool import TARGETS_DIRECTORY_NAME
from taf.exceptions import (
    GitError,
    MissingHostsError,
    InvalidHostsError,
)
from taf.log import taf_logger
import taf.repositoriesdb as repositoriesdb

_hosts_dict = {}

DEPENDENCIES_JSON_PATH = f"{TARGETS_DIRECTORY_NAME}/dependencies.json"
MIRRORS_JSON_PATH = f"{TARGETS_DIRECTORY_NAME}/mirrors.json"
REPOSITORIES_JSON_PATH = f"{TARGETS_DIRECTORY_NAME}/repositories.json"
HOSTS_JSON_PATH = f"{TARGETS_DIRECTORY_NAME}/hosts.json"
AUTH_REPOS_HOSTS_KEY = "auth_repos"


class Host:
    def __init__(self, name):
        self.name = name
        self.data_by_auth_repo = {}

    def to_json_dict(self):
        return {"name": self.name, "data": self.data_by_auth_repo}


def load_hosts(root_auth_repo, repos_and_commits):
    """
    Read hosts files of all repositories in the hierarchy and group repositories by hosts
    One repository can belong to more than one host and one host can contain more than one
    repository. Populate global hosts dictionary. get_hosts function can later be used to get
    loaded losts.

    For now, only read the hosts files given the top commits
    The question is if it even makes sense to read older hosts date - in any case, not a high priority
    """
    # keep track of traversed repositories in case there are circular dependencies
    # also keep a track of loaded repositories per host, in case there are multiple
    # hosts.json files which define the same repo and host
    # TODO
    # should one overwrite another one or is this an error?
    # raise and error for now
    _load_hosts(root_auth_repo, repos_and_commits, set(), {})


def _load_hosts(
    auth_repo, repos_and_commits, traversed_repos, loaded_repositories_per_host
):

    global _hosts_dict
    if auth_repo.name in traversed_repos:
        return

    traversed_repos.add(auth_repo.name)
    # load based on the last validated commit
    # if the repository did not exist and could not be validated, there should be no commit
    # skip such repositories
    commit = repos_and_commits[auth_repo.name]
    if commit is None:
        return
    try:
        hosts_data = _get_json_file(auth_repo, HOSTS_JSON_PATH, commit)
    except MissingHostsError:
        # if the current repository does not contain a host file, still check its dependencies
        hosts_data = {}

    child_repos = repositoriesdb.get_deduplicated_auth_repositories(auth_repo, [commit])
    for host_name, host_data in hosts_data.items():
        host = _hosts_dict.setdefault(host_name, Host(host_name))
        # if a host is defined in more than one authentication repository
        # combine all information
        # this is a dictionary which contains names of authentication repositories
        # and some optional additional information
        auth_repos = host_data[AUTH_REPOS_HOSTS_KEY]
        custom = host_data.get("custom")
        # if this is called from the updater, the same repositories used in the updater will be returned
        # unless the dependencies database is explicitly cleared
        repositoriesdb.load_dependencies(
            auth_repo,
            library_dir=auth_repo.library_dir,
            commits=[commit],
        )
        host_repos = []
        # iterate through repositories defined in dependencies.json
        # skip the ones that are not
        # collect information defined in hosts.json
        for child_repo_name, child_repo in child_repos.items():
            if child_repo_name in auth_repos:
                loaded_repos_of_host = loaded_repositories_per_host.setdefault(
                    host_name, []
                )
                if child_repo.name in loaded_repos_of_host:
                    raise InvalidHostsError(
                        f"Host {host_name} and repo {child_repo.name} defined in multiple places"
                    )
                loaded_repos_of_host.append(child_repo.name)
                repo_custom = auth_repos[child_repo.name]
                # add additional repo information specified in the hosts file to the repositories' custom dictionary
                # if the data was already added to the custom dictionary, it will just be overwritten by the same data
                host_repos.append(
                    {child_repo.name: {"auth_repo": child_repo, "custom": repo_custom}}
                )
        auth_repo_host_data = {"auth_repos": host_repos, "custom": custom}
        host.data_by_auth_repo[auth_repo] = auth_repo_host_data

    for child_repo in child_repos.values():
        # recursively load hosts
        # we do not expect a very large hierarchy, so no need to create a stack based implementation
        _load_hosts(
            child_repo, repos_and_commits, traversed_repos, loaded_repos_of_host
        )


def get_hosts():
    return _hosts_dict.values()


def set_hosts_of_repo(auth_repo, hosts):
    hosts_of_repo = {}
    for hosts_info in hosts:
        for host, host_data in hosts_info.items():
            if auth_repo.name not in host_data[AUTH_REPOS_HOSTS_KEY]:
                continue
            data = host_data.copy()
            repo_custom = host_data[AUTH_REPOS_HOSTS_KEY][auth_repo.name]
            data.pop(AUTH_REPOS_HOSTS_KEY)
            if len(repo_custom):
                data["auth_repo"] = repo_custom
            hosts_of_repo[host] = data
    if not len(hosts_of_repo):
        taf_logger.warning(
            "Host of authentication repository {} not specified", auth_repo.name
        )
    auth_repo.hosts = hosts_of_repo


def load_hosts_json(auth_repo, commit=None):
    if commit is None:
        commit = auth_repo.top_commit_of_branch(auth_repo.default_branch)
    try:
        return _get_json_file(auth_repo, HOSTS_JSON_PATH, commit)
    except MissingHostsError:
        return {}


def _get_json_file(auth_repo, path, commit):
    try:
        return auth_repo.get_json(commit, path)
    except GitError:
        raise MissingHostsError(f"{path} not available at revision {commit}")
    except json.decoder.JSONDecodeError:
        raise InvalidHostsError(f"{path} not a valid json at revision {commit}")
