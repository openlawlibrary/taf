import json
from pathlib import Path

from taf.exceptions import (
    InvalidOrMissingMetadataError,
    RepositoriesNotFoundError,
    RepositoryInstantiationError,
    GitError,
)
from taf.git import NamedGitRepository
from taf.log import taf_logger

# {
#     'authentication_repo_name': {
#         'commit' : {
#             'path1': git_repository1
#             'path2': target_git_repository2
#             ...
#         }
#     }
# }

_repositories_dict = {}
REPOSITORIES_JSON_PATH = "targets/repositories.json"
MIRRORS_JSON_PATH = "targets/mirrors.json"


def clear_repositories_db():
    global _repositories_dict
    _repositories_dict.clear()


def load_repositories(
    auth_repo,
    repo_classes=None,
    factory=None,
    root_dir=None,
    only_load_targets=True,
    commits=None,
    roles=None,
):
    """
    Creates target repositories by reading repositories.json and targets.json files
    at the specified revisions, given an authentication repo.
    If the the commits are not specified, targets will be created based on the HEAD pointer
    of the authentication repository. It is possible to specify git repository class that
    will be created per target.
    Args:
        auth_repo: the authentication repository
        target_classes: a single git repository class, or a dictionary whose keys are
        target paths and values are git repository classes. E.g:
        {
            'path1': GitRepo1,
            'path2': GitRepo2,
            'default': GitRepo3
        }
        When determening a target's class, in case when targets_classes is a dictionary,
        it is first checked if its path is in a key in the dictionary. If it is not found,
        it is checked if default class is set, by looking up value of 'default'. If nothing
        is found, the class is set to TAF's NamedGitRepository.
        If target_classes is a single class, all targets will be of that type.
        If target_classes is None, all targets will be of TAF's NamedGitRepository type.
        root_dir: root directory relative to which the target paths are specified
        commits: Authentication repository's commits at which to read targets.json
        only_load_targets: specifies if only repositories specified in targets files should be loaded.
        If set to false, all repositories defined in repositories.json are loaded, regardless of if
        they are targets or not.
        roles: a list of roles whose repositories should be loaded. The repositories linked to a specific
        role are determined based on its targets, so there is no need to set only_load_targets to True.
        If only_load_targets is True and roles is not set, all roles will be taken into consideration.
    """
    global _repositories_dict
    if auth_repo.path not in _repositories_dict:
        _repositories_dict[auth_repo.path] = {}

    if commits is None:
        auth_repo_head_commit = auth_repo.head_commit_sha()
        if auth_repo_head_commit is None:
            taf_logger.info(
                "Authentication repository does not exist - cannot load target repositories"
            )
            return
        commits = [auth_repo_head_commit]

    taf_logger.debug(
        "Loading {}'s target repositories at revisions {}",
        auth_repo.path,
        ", ".join(commits),
    )

    if root_dir is None:
        root_dir = Path(auth_repo.path).parent.parent

    if roles is not None and len(roles):
        only_load_targets = True

    for commit in commits:
        repositories_dict = {}
        # check if already loaded
        if commit in _repositories_dict[auth_repo.path]:
            continue

        _repositories_dict[auth_repo.path][commit] = repositories_dict

        repositories = _load_repositories_json(auth_repo, commit)
        if repositories is None:
            continue

        mirrors = _load_mirrors_json(auth_repo, commit)

        # target repositories are defined in both mirrors.json and targets.json
        repositories = repositories["repositories"]
        targets = _targets_of_roles(auth_repo, commit, roles)

        for path, repo_data in repositories.items():
            urls = _get_urls(mirrors, path, repo_data)
            if path not in targets and only_load_targets:
                continue

            additional_info = _get_custom_data(repo_data, targets.get(path))

            git_repo = None
            try:
                if factory is not None:
                    git_repo = factory(root_dir, path, urls, additional_info)
                else:
                    git_repo_class = _determine_repo_class(repo_classes, path)
                    git_repo = git_repo_class(root_dir, path, urls, additional_info)
            except Exception as e:
                taf_logger.error(
                    "Auth repo {}: an error occurred while instantiating repository {}: {}",
                    auth_repo.path,
                    path,
                    str(e),
                )
                raise RepositoryInstantiationError(f"{root_dir / path}", str(e))

            # allows us to partially update repositories
            if git_repo:
                if not isinstance(git_repo, NamedGitRepository):
                    raise Exception(
                        f"{type(git_repo)} is not a subclass of NamedGitRepository"
                    )

                repositories_dict[path] = git_repo

        taf_logger.debug(
            "Loaded the following repositories at revision {}: {}",
            commit,
            ", ".join(repositories_dict.keys()),
        )


def _determine_repo_class(repo_classes, path):
    # if no class is specified, return the default one
    if repo_classes is None:
        return NamedGitRepository

    # if only one value is specified, that means that all target repositories
    # should be of the same class
    if not isinstance(repo_classes, dict):
        return repo_classes

    if path in repo_classes:
        return repo_classes[path]

    if "default" in repo_classes:
        return repo_classes["default"]

    return NamedGitRepository


def _get_custom_data(repo, target):
    custom = repo.get("custom", {})
    target_custom = target.get("custom") if target is not None else None
    if target_custom is not None:
        custom.update(target_custom)
    return custom


def _get_json_file(auth_repo, path, commit):
    try:
        return auth_repo.get_json(commit, path)
    except GitError:
        raise InvalidOrMissingMetadataError(
            f"{path} not available at revision {commit}"
        )
    except json.decoder.JSONDecodeError:
        raise InvalidOrMissingMetadataError(
            f"{path} not a valid json at revision {commit}"
        )


def _get_urls(mirrors, repo_path, repo_data):
    if "urls" in repo_data:
        return repo_data["urls"]
    elif mirrors is None:
        raise RepositoryInstantiationError(
            repo_path,
            f"{MIRRORS_JSON_PATH} does not exists or is not valid and no urls of {repo_path} specified in {REPOSITORIES_JSON_PATH}",
        )

    try:
        org_name, repo_name = repo_path.split("/")
    except Exception:
        raise RepositoryInstantiationError(
            repo_path, "repository name is not in the org_name/repo_name format"
        )

    return [mirror.format(org_name=org_name, repo_name=repo_name) for mirror in mirrors]


def get_repositories_paths_by_custom_data(auth_repo, commit=None, **custom):
    if not commit:
        commit = auth_repo.head_commit_sha()
    taf_logger.debug(
        "Auth repo {}: finding paths of repositories by custom data {}",
        auth_repo.path,
        custom,
    )
    repositories = auth_repo.get_json(commit, REPOSITORIES_JSON_PATH)
    repositories = repositories["repositories"]
    targets = _targets_of_roles(auth_repo, commit)

    def _compare(path):
        # Check if `custom` dict is subset of targets[path]['custom'] dict
        try:
            return (
                custom.items()
                <= _get_custom_data(repositories[path], targets.get(path)).items()
            )
        except (AttributeError, KeyError):
            return False

    paths = list(filter(_compare, repositories)) if custom else list(repositories)
    if len(paths):
        taf_logger.debug(
            "Auth repo {}: found the following paths {}", auth_repo.path, paths
        )
        return paths
    taf_logger.error(
        "Auth repo {}: repositories associated with custom data {} not found",
        auth_repo.path,
        custom,
    )
    raise RepositoriesNotFoundError(
        f"Repositories associated with custom data {custom} not found"
    )


def get_deduplicated_repositories(auth_repo, commits):
    global _repositories_dict
    taf_logger.debug(
        "Auth repo {}: getting a deduplicated list of repositories", auth_repo.path
    )
    all_repositories = _repositories_dict.get(auth_repo.path)
    if all_repositories is None:
        taf_logger.error(
            "Repositories defined in authentication repository {} have not been loaded",
            auth_repo.path,
        )
        raise RepositoriesNotFoundError(
            "Repositories defined in authentication repository"
            f" {auth_repo.path} have not been loaded"
        )
    repositories = {}
    # persuming that the newest commit is the last one
    for commit in commits:
        if commit not in all_repositories:
            taf_logger.error(
                "Repositories defined in authentication repository {} at revision {} have "
                "not been loaded",
                auth_repo.path,
                commit,
            )
            raise RepositoriesNotFoundError(
                "Repositories defined in authentication repository "
                "{auth_repo.path} at revision {commit} have not been loaded"
            )
        for path, repo in all_repositories[commit].items():
            # will overwrite older repo with newer
            repositories[path] = repo

    taf_logger.debug(
        "Auth repo {}: deduplicated list of repositories {}",
        auth_repo.path,
        ", ".join(repositories.keys()),
    )
    return repositories


def get_repository(auth_repo, path, commit=None):
    return get_repositories(auth_repo, commit).get(path)


def get_repositories(auth_repo, commit=None):
    global _repositories_dict
    if commit is None:
        commit = auth_repo.head_commit_sha()
    taf_logger.debug(
        "Auth repo {}: finding repositories defined at commit {}",
        auth_repo.path,
        commit,
    )
    all_repositories = _repositories_dict.get(auth_repo.path)
    if all_repositories is None:
        taf_logger.error(
            "Repositories defined in authentication repository {} have not been loaded",
            auth_repo.path,
        )
        raise RepositoriesNotFoundError(
            "Repositories defined in authentication repository"
            f" {auth_repo.path} have not been loaded"
        )

    repositories = all_repositories.get(commit)
    if repositories is None:
        taf_logger.error(
            "Repositories defined in authentication repository {} at revision {} have "
            "not been loaded",
            auth_repo.path,
            commit,
        )
        raise RepositoriesNotFoundError(
            "Repositories defined in authentication repository "
            f"{auth_repo.path} at revision {commit} have not been loaded"
        )
    taf_logger.debug(
        "Auth repo {}: found the following repositories at revision {}: {}",
        auth_repo.path,
        commit,
        ", ".join(repositories.keys()),
    )
    return repositories


def get_repositories_by_custom_data(auth_repo, commit=None, **custom_data):
    taf_logger.debug(
        "Auth repo {}: finding repositories by custom data {}",
        auth_repo.path,
        custom_data,
    )
    repositories = get_repositories(auth_repo, commit).values()

    def _compare(repo):
        # Check if `custom` dict is subset of targets[path]['custom'] dict
        try:
            return custom_data.items() <= repo.additional_info.items()
        except (AttributeError, KeyError):
            return False

    found_repos = (
        list(filter(_compare, repositories)) if custom_data else list(repositories)
    )

    if len(found_repos):
        taf_logger.debug(
            "Auth repo {}: found the following repositories {}",
            auth_repo.path,
            repositories,
        )
        return found_repos
    taf_logger.error(
        "Auth repo {}: repositories associated with custom data {} not found",
        auth_repo.path,
        custom_data,
    )
    raise RepositoriesNotFoundError(
        f"Repositories associated with custom data {custom_data} not found"
    )


def _load_repositories_json(auth_repo, commit):
    try:
        return _get_json_file(auth_repo, REPOSITORIES_JSON_PATH, commit)
    except InvalidOrMissingMetadataError as e:
        if f"{REPOSITORIES_JSON_PATH} not available at revision" in str(e):
            taf_logger.debug("Skipping commit {} due to: {}", commit, str(e))
            return None
        else:
            raise


def _load_mirrors_json(auth_repo, commit):
    try:
        return _get_json_file(auth_repo, MIRRORS_JSON_PATH, commit).get("mirrors")
    except InvalidOrMissingMetadataError:
        taf_logger.debug(
            "{} not available at revision {}. Expecting to find urls in {}",
            MIRRORS_JSON_PATH,
            commit,
            REPOSITORIES_JSON_PATH,
        )
        return None


def _targets_of_roles(auth_repo, commit, roles=None):

    with auth_repo.repository_at_revision(commit):
        return auth_repo.get_singed_targets_with_custom_data(roles)


def repositories_loaded(auth_repo):
    all_repositories = _repositories_dict.get(auth_repo.path)
    if all_repositories is None or not len(all_repositories):
        return False
    return any(
        len(repositories_at_commit)
        for repositories_at_commit in all_repositories.values()
    )
