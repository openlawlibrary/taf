import json
from pathlib import Path
from subprocess import CalledProcessError

import taf.log
from taf.exceptions import InvalidOrMissingMetadataError, RepositoriesNotFoundError
from taf.git import NamedGitRepository

# {
#     'authentication_repo_name': {
#         'commit' : {
#             'path1': git_repository1
#             'path2': target_git_repository2
#             ...
#         }
#     }
# }

logger = taf.log.get_logger(__name__)

_repositories_dict = {}
repositories_path = "targets/repositories.json"
targets_path = "metadata/targets.json"


def clear_repositories_db():
    global _repositories_dict
    _repositories_dict.clear()


def load_repositories(
    auth_repo,
    repo_classes=None,
    factory=None,
    root_dir=None,
    only_load_targets=False,
    commits=None,
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
        only_load_targets: specifies if only repositories specified in targets.json should be loaded.
        If set to false, all repositories defined in repositories.json are loaded, regardless of if
        they are targets or not.
    """

    global _repositories_dict
    if auth_repo.repo_name not in _repositories_dict:
        _repositories_dict[auth_repo.repo_name] = {}

    if commits is None:
        commits = [auth_repo.head_commit_sha()]

    logger.debug(
        "Loading %s's target repositories at revisions %s",
        auth_repo.repo_name,
        ", ".join(commits),
    )

    if root_dir is None:
        root_dir = Path(auth_repo.repo_path).parent

    for commit in commits:
        repositories_dict = {}
        # check if already loaded
        if commit in _repositories_dict[auth_repo.repo_name]:
            continue

        _repositories_dict[auth_repo.repo_name][commit] = repositories_dict
        try:
            repositories = _get_json_file(auth_repo, repositories_path, commit)
            targets = _get_json_file(auth_repo, targets_path, commit)
        except InvalidOrMissingMetadataError as e:
            logger.warning("Skipping commit %s due to error %s", commit, e)
            continue

        # target repositories are defined in both mirrors.json and targets.json
        repositories = repositories["repositories"]
        targets = targets["signed"]["targets"]
        for path, repo_data in repositories.items():
            urls = repo_data["urls"]
            target = targets.get(path)
            if target is None and only_load_targets:
                continue
            additional_info = _get_custom_data(repo_data, targets.get(path))

            if factory is not None:
                git_repo = factory(root_dir, path, urls, additional_info)
            else:
                git_repo_class = _determine_repo_class(repo_classes, path)
                git_repo = git_repo_class(root_dir, path, urls, additional_info)

            if not isinstance(git_repo, NamedGitRepository):
                raise Exception(
                    f"{type(git_repo)} is not a subclass of NamedGitRepository"
                )

            repositories_dict[path] = git_repo

        logger.debug(
            "Loaded the following repositories at revision %s: %s",
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
    except CalledProcessError:
        raise InvalidOrMissingMetadataError("{path} not available at revision {commit}")
    except json.decoder.JSONDecodeError:
        raise InvalidOrMissingMetadataError(
            "{path} not a valid json at revision {commit}"
        )


def get_repositories_paths_by_custom_data(auth_repo, commit=None, **custom):
    if not commit:
        commit = auth_repo.head_commit_sha()
    logger.debug(
        "Auth repo %s: finding paths of repositories by custom data %s",
        auth_repo.repo_name,
        custom,
    )
    targets = auth_repo.get_json(commit, targets_path)
    repositories = auth_repo.get_json(commit, repositories_path)
    repositories = repositories["repositories"]
    targets = targets["signed"]["targets"]

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
        logger.debug(
            "Auth repo %s: found the following paths %s", auth_repo.repo_name, paths
        )
        return paths
    logger.error(
        "Auth repo %s: repositories associated with custom data %s not found",
        auth_repo.repo_name,
        custom,
    )
    raise RepositoriesNotFoundError(
        f"Repositories associated with custom data {custom} not found"
    )


def get_deduplicated_repositories(auth_repo, commits):
    global _repositories_dict
    logger.debug(
        "Auth repo %s: getting a deduplicated list of repositories", auth_repo.repo_name
    )
    all_repositories = _repositories_dict.get(auth_repo.repo_name)
    if all_repositories is None:
        logger.error(
            "Repositories defined in authentication repository %s have not been loaded",
            auth_repo.repo_name,
        )
        raise RepositoriesNotFoundError(
            "Repositories defined in authentication repository"
            f" {auth_repo.repo_name} have not been loaded"
        )
    repositories = {}
    # persuming that the newest commit is the last one
    for commit in commits:
        if commit not in all_repositories:
            logger.error(
                "Repositories defined in authentication repository %s at revision %s have "
                "not been loaded",
                auth_repo.repo_name,
                commit,
            )
            raise RepositoriesNotFoundError(
                "Repositories defined in authentication repository "
                "{auth_repo.repo_name} at revision {commit} have not been loaded"
            )
        for path, repo in all_repositories[commit].items():
            # will overwrite older repo with newer
            repositories[path] = repo

    logger.debug(
        "Auth repo %s: deduplicated list of repositories %s",
        auth_repo.repo_name,
        ", ".join(repositories.keys()),
    )
    return repositories


def get_repository(auth_repo, path, commit=None):
    return get_repositories(auth_repo, commit)[path]


def get_repositories(auth_repo, commit=None):
    global _repositories_dict
    if commit is None:
        commit = auth_repo.head_commit_sha()
    logger.debug(
        "Auth repo %s: finding repositories defined at commit %s",
        auth_repo.repo_name,
        commit,
    )
    all_repositories = _repositories_dict.get(auth_repo.repo_name)
    if all_repositories is None:
        logger.error(
            "Repositories defined in authentication repository %s have not been loaded",
            auth_repo.repo_name,
        )
        raise RepositoriesNotFoundError(
            "Repositories defined in authentication repository"
            f" {auth_repo.repo_name} have not been loaded"
        )

    repositories = all_repositories.get(commit)
    if repositories is None:
        logger.error(
            "Repositories defined in authentication repository %s at revision %s have "
            "not been loaded",
            auth_repo.repo_name,
            commit,
        )
        raise RepositoriesNotFoundError(
            "Repositories defined in authentication repository "
            f"{auth_repo.repo_name} at revision {commit} have not been loaded"
        )
    logger.debug(
        "Auth repo %s: found the following repositories at revision %s: %s",
        auth_repo.repo_name,
        commit,
        ", ".join(repositories.keys()),
    )
    return repositories


def get_repositories_by_custom_data(auth_repo, commit=None, **custom_data):
    logger.debug(
        "Auth repo %s: finding repositories by custom data %s",
        auth_repo.repo_name,
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
        logger.debug(
            "Auth repo %s: found the following repositories %s",
            auth_repo.repo_name,
            repositories,
        )
        return found_repos
    logger.error(
        "Auth repo %s: repositories associated with custom data %s not found",
        auth_repo.repo_name,
        custom_data,
    )
    raise RepositoriesNotFoundError(
        f"Repositories associated with custom data {custom_data} not found"
    )
