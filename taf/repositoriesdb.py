import json
from typing import Callable, Dict, List, Optional, Type
import fnmatch
from pathlib import Path
from taf.auth_repo import AuthenticationRepository
from taf.constants import TARGETS_DIRECTORY_NAME
from taf.exceptions import (
    InvalidOrMissingMetadataError,
    RepositoriesNotFoundError,
    RepositoryInstantiationError,
    GitError,
    TAFError,
)
from taf.git import GitRepository
from taf.log import taf_logger
from taf.models.types import Commitish


# Target repositories db

# {
#     'authentication_repo_path': {
#         'commit' : {
#             'name1': git_repository1
#             'name2': target_git_repository2
#             ...
#         }
#     }
# }

_repositories_dict: Dict = {}
_dependencies_dict: Dict = {}
REPOSITORIES_JSON_NAME = "repositories.json"
DEPENDENCIES_JSON_NAME = "dependencies.json"
MIRRORS_JSON_NAME = "mirrors.json"
DEPENDENCIES_JSON_PATH = f"{TARGETS_DIRECTORY_NAME}/{DEPENDENCIES_JSON_NAME}"
MIRRORS_JSON_PATH = f"{TARGETS_DIRECTORY_NAME}/{MIRRORS_JSON_NAME}"
REPOSITORIES_JSON_PATH = f"{TARGETS_DIRECTORY_NAME}/{REPOSITORIES_JSON_NAME}"


def clear_repositories_db():
    global _repositories_dict
    _repositories_dict.clear()


def clear_dependencies_db():
    global _dependencies_dict
    _dependencies_dict.clear()


def check_if_repositories_json_exists(
    auth_repo: AuthenticationRepository, commit: Optional[Commitish] = None
) -> bool:
    if commit is None:
        commit = auth_repo.head_commit()
        if commit is None:
            raise GitError(
                auth_repo,
                message="Could not check if repositroies.json exists. Commit is not specified and head commit could not be determined",
            )
    try:
        auth_repo.get_json(commit, REPOSITORIES_JSON_PATH)
        return True
    except GitError:
        return False


def load_dependencies(
    auth_repo: AuthenticationRepository,
    auth_class: Type = AuthenticationRepository,
    library_dir: Optional[str] = None,
    commits: Optional[List[Commitish]] = None,
) -> None:
    global _dependencies_dict

    new_deps = _load_dependencies(
        auth_repo=auth_repo,
        auth_class=auth_class,
        library_dir=library_dir,
        commits=commits,
    )
    if auth_repo.path in _dependencies_dict:
        _dependencies_dict[auth_repo.path].update(new_deps)
    else:
        _dependencies_dict[auth_repo.path] = new_deps


def _load_dependencies(
    auth_repo: AuthenticationRepository,
    auth_class: Type = AuthenticationRepository,
    library_dir: Optional[str] = None,
    commits: Optional[List[Commitish]] = None,
) -> Dict:

    dependencies = {}
    if commits is None:
        auth_repo_head_commit = auth_repo.head_commit()
        if auth_repo_head_commit is None:
            taf_logger.info(
                "Authentication repository does not exist - cannot load included authentication repositories"
            )
            return {}
        commits = [auth_repo_head_commit]

    taf_logger.debug(
        "Loading {}'s included authentication repositories at revisions {}",
        auth_repo.path,
        ", ".join([commit.value for commit in commits]),
    )

    if library_dir is None:
        library_dir = str(Path(auth_repo.path).parent.parent)

    mirrors = load_mirrors_json(auth_repo, commits[-1])
    for commit in commits:
        commit_dependencies: Dict = {}

        dependencies[commit] = commit_dependencies

        dependencies_json = load_dependencies_json(auth_repo, commit)
        if dependencies_json is None:
            continue

        dependencies_json = dependencies_json["dependencies"]
        if dependencies_json is None:
            continue

        for name, repo_data in dependencies_json.items():
            try:
                if mirrors:
                    urls = _get_urls(mirrors, name, repo_data)
                else:
                    urls = [name]
            except RepositoryInstantiationError:
                commit_dependencies.clear()
                break

            out_of_band_authentication = repo_data.get("out-of-band-authentication")
            custom = _get_custom_data(repo_data, None)
            default_branch = repo_data.get("branch") or auth_repo.default_branch

            if auth_class is None:
                auth_class = AuthenticationRepository
            else:
                if not issubclass(auth_class, AuthenticationRepository):
                    raise Exception(
                        f"{auth_class} is not a subclass of AuthenticationRepository"
                    )
            contained_auth_repo = None
            try:
                # TODO check if repo class is subclass of AuthenticationRepository
                # or will that get caught by except
                contained_auth_repo = auth_class(
                    library_dir=library_dir,
                    name=name,
                    urls=urls,
                    out_of_band_authentication=out_of_band_authentication,
                    default_branch=default_branch,
                    custom=custom,
                )
            except Exception as e:
                taf_logger.error(
                    "Auth repo {}: an error occurred while instantiating repository {}: {}",
                    auth_repo.path,
                    name,
                    str(e),
                )
                raise RepositoryInstantiationError(str(Path(library_dir, name)), str(e))
            commit_dependencies[name] = contained_auth_repo

        taf_logger.debug(
            "Loaded the following contained authentication repositories at revision {}: {}",
            commit,
            ", ".join(commit_dependencies.keys()),
        )
    return dependencies


def load_repositories(
    auth_repo: AuthenticationRepository,
    repo_classes: Optional[Type] = None,
    factory: Optional[Callable] = None,
    library_dir: Optional[str] = None,
    only_load_targets: bool = True,
    commits: Optional[List[Commitish]] = None,
    roles: Optional[List[str]] = None,
    excluded_target_globs: Optional[List[str]] = None,
    raise_error_if_no_urls: bool = False,
) -> None:
    """
    Creates target repositories by reading repositories.json and targets.json files
    at the specified revisions, given an authentication repo.
    If the the commits are not specified, targets will be created based on the HEAD pointer
    of the authentication repository. It is possible to specify git repository class that
    will be created per target.
    Args:
        auth_repo: the authentication repository
        target_classes: a single git repository class, or a dictionary whose keys are
        target names and values are git repository classes. E.g:
        {
            'name1': GitRepo1,
            'name2': GitRepo2,
            'default': GitRepo3
        }
        When determining a target's class, in case when targets_classes is a dictionary,
        it is first checked if its name is in a key in the dictionary. If it is not found,
        it is checked if default class is set, by looking up value of 'default'. If nothing
        is found, the class is set to TAF's GitRepository.
        If target_classes is a single class, all targets will be of that type.
        If target_classes is None, all targets will be of TAF's GitRepository type.
        library_dir: root directory relative to which the target names are specified
        commits: Authentication repository's commits at which to read targets.json
        only_load_targets: specifies if only repositories specified in targets files should be loaded.
        If set to false, all repositories defined in repositories.json are loaded, regardless of if
        they are targets or not.
        roles: a list of roles whose repositories should be loaded. The repositories linked to a specific
        role are determined based on its targets, so there is no need to set only_load_targets to True.
        If only_load_targets is True and roles is not set, all roles will be taken into consideration.
    """
    global _repositories_dict
    new_reps = _load_repositories(
        auth_repo=auth_repo,
        repo_classes=repo_classes,
        factory=factory,
        library_dir=library_dir,
        only_load_targets=only_load_targets,
        commits=commits,
        roles=roles,
        excluded_target_globs=excluded_target_globs,
        raise_error_if_no_urls=raise_error_if_no_urls,
    )
    if commits is None or len(commits) == 0:
        commit = auth_repo.head_commit()
        if commit is None:
            return
        commits = [commit]
    if auth_repo.path in _repositories_dict:
        for commit in commits:
            if commit not in _repositories_dict[auth_repo.path]:
                _repositories_dict[auth_repo.path][commit] = new_reps[commit]
    else:
        _repositories_dict[auth_repo.path] = new_reps


def _load_repositories(
    auth_repo: AuthenticationRepository,
    repo_classes: Optional[Type] = None,
    factory: Optional[Callable] = None,
    library_dir: Optional[str] = None,
    only_load_targets: bool = True,
    commits: Optional[List[Commitish]] = None,
    roles: Optional[List[str]] = None,
    excluded_target_globs: Optional[List[str]] = None,
    raise_error_if_no_urls: Optional[bool] = False,
) -> Dict:

    repositories = {}
    if excluded_target_globs is None:
        excluded_target_globs = []

    if commits is None:
        auth_repo_head_commit = auth_repo.head_commit()
        if auth_repo_head_commit is None:
            taf_logger.info(
                "Authentication repository does not exist - cannot load target repositories"
            )
            return {}
        commits = [auth_repo_head_commit]

    taf_logger.debug(
        "Loading {}'s target repositories at revisions {}",
        auth_repo.path,
        ", ".join([commit.value for commit in commits]),
    )

    if library_dir is None:
        library_dir = str(Path(auth_repo.path).parent.parent)

    if roles is not None and len(roles):
        only_load_targets = True

    skipped_targets = []
    mirrors = load_mirrors_json(auth_repo, commits[-1])
    for commit in commits:
        commit_repositories: Dict = {}

        repositories[commit] = commit_repositories

        repositories_json = load_repositories_json(auth_repo, commit)
        if repositories_json is None:
            continue

        # target repositories are defined in both repositories.json and targets.json
        repositories_json = repositories_json["repositories"]
        if repositories_json is None:
            continue
        targets = _targets_of_roles(auth_repo, commit, roles)

        for name, repo_data in repositories_json.items():
            if name in skipped_targets:
                continue
            if name not in targets and only_load_targets:
                continue
            if any(
                fnmatch.fnmatch(name, excluded_target_glob)
                for excluded_target_glob in excluded_target_globs
            ):
                skipped_targets.append(name)
                continue
            custom = _get_custom_data(repo_data, targets.get(name))
            urls = _get_urls(mirrors, name, repo_data, raise_error_if_no_urls)
            default_branch = _get_target_default_branch(auth_repo, name, commit)
            git_repo = _initialize_repository(
                factory,
                repo_classes,
                urls,
                custom,
                library_dir,
                name,
                default_branch,
                auth_repo,
            )
            if git_repo:
                commit_repositories[name] = git_repo

        taf_logger.debug(
            "Loaded the following repositories at revision {}: {}",
            commit,
            ", ".join(commit_repositories.keys()),
        )
    return repositories


def _determine_repo_class(repo_classes, name):
    # if no class is specified, return the default one
    if repo_classes is None:
        return GitRepository

    # if only one value is specified, that means that all target repositories
    # should be of the same class
    if not isinstance(repo_classes, dict):
        return repo_classes

    if name in repo_classes:
        return repo_classes[name]

    if "default" in repo_classes:
        return repo_classes["default"]

    return GitRepository


def _get_custom_data(repo, target):
    custom = repo.get("custom", {})
    target_custom = target.get("custom") if target is not None else None
    if target_custom is not None:
        custom.update(target_custom)
    return custom


def _get_json_file(auth_repo: AuthenticationRepository, name: str, commit: Commitish):
    try:
        return auth_repo.get_json(commit, name)
    except GitError:
        raise InvalidOrMissingMetadataError(
            f"{name} not available at revision {commit}"
        )
    except json.decoder.JSONDecodeError:
        raise InvalidOrMissingMetadataError(
            f"{name} not a valid json at revision {commit}"
        )


def _get_urls(
    mirrors, repo_name, repo_data=None, raise_error_if_no_mirrors=False
) -> List[str]:
    if repo_data is not None and "urls" in repo_data:
        return repo_data["urls"]
    elif mirrors is None:
        if raise_error_if_no_mirrors:
            raise RepositoryInstantiationError(
                repo_name,
                f"{MIRRORS_JSON_PATH} does not exists or is not valid and no urls of {repo_name} specified in {REPOSITORIES_JSON_PATH}",
            )
        return []

    try:
        org_name, repo_name = repo_name.split("/")
    except Exception:
        raise RepositoryInstantiationError(
            repo_name, "repository name is not in the org_name/repo_name format"
        )

    return [mirror.format(org_name=org_name, repo_name=repo_name) for mirror in mirrors]


def _get_target_default_branch(
    auth_repo: AuthenticationRepository, name: str, commit: Commitish
) -> Optional[str]:
    """
    Gets signed name of branch for a target repository by loading json at specified <commit>.
    If successful, signed branch name is considered a default branch when instantiating a target git repository.
    Otherwise, when no branch key is found under signed targets, the default branch is inherited from authentication repository.
    """
    try:
        target = auth_repo.get_target(name, commit)
        if target is None:
            default_branch = None
        else:
            default_branch = target.get("branch")
    except (KeyError, AttributeError):
        default_branch = None

    if default_branch is None:
        default_branch = auth_repo.default_branch
    return default_branch


def get_repositories_paths_by_custom_data(
    auth_repo: AuthenticationRepository, commit: Optional[Commitish] = None, **custom
) -> Optional[List[str]]:
    if not commit:
        commit = auth_repo.head_commit()
        if commit is None:
            raise TAFError(
                "Could not get repositories. Commit is not specified and head commit could not be determined"
            )

    taf_logger.debug(
        "Auth repo {}: finding names of repositories by custom data {}",
        auth_repo.path,
        custom,
    )
    repositories = auth_repo.get_json(commit, REPOSITORIES_JSON_PATH)
    if repositories is None:
        return None
    repositories = repositories["repositories"]
    if repositories is None:
        return None
    targets = _targets_of_roles(auth_repo, commit)

    def _compare(name):
        # Check if `custom` dict is subset of targets[name]['custom'] dict
        try:
            return (
                custom.items()
                <= _get_custom_data(repositories[name], targets.get(name)).items()
            )
        except (AttributeError, KeyError):
            return False

    names = list(filter(_compare, repositories)) if custom else list(repositories)
    if len(names):
        taf_logger.debug(
            "Auth repo {}: found the following names {}", auth_repo.path, names
        )
        return names
    taf_logger.error(
        "Auth repo {}: repositories associated with custom data {} not found",
        auth_repo.path,
        custom,
    )
    raise RepositoriesNotFoundError(
        f"Repositories associated with custom data {custom} not found"
    )


def get_deduplicated_auth_repositories(
    auth_repo: AuthenticationRepository,
    commits: Optional[List[Commitish]],
) -> Dict[str, AuthenticationRepository]:
    return _get_deduplicated_target_or_auth_repositories(auth_repo, commits, True)


def get_deduplicated_repositories(
    auth_repo: AuthenticationRepository,
    commits: Optional[List[Commitish]] = None,
    excluded_target_globs: Optional[List[str]] = None,
    library_dir: Optional[str] = None,
    raise_error_if_no_urls=False,
) -> Dict[str, GitRepository]:
    return _get_deduplicated_target_or_auth_repositories(
        auth_repo,
        commits,
        False,
        excluded_target_globs,
        library_dir,
        raise_error_if_no_urls,
    )


def _get_deduplicated_target_or_auth_repositories(
    auth_repo: AuthenticationRepository,
    commits: Optional[List[Commitish]],
    load_auth: Optional[bool] = False,
    excluded_target_globs: Optional[List[str]] = None,
    library_dir: Optional[str] = None,
    raise_error_if_no_urls: Optional[bool] = False,
):
    if commits is None:
        head_commit = auth_repo.head_commit()
        if not head_commit:
            return {}
        commits = [head_commit]

    if load_auth:
        if auth_repo.path in _dependencies_dict and all(
            commit in _dependencies_dict[auth_repo.path] for commit in commits
        ):
            loaded_repositories_dict = _dependencies_dict
        else:
            loaded_repositories_dict = {
                auth_repo.path: _load_dependencies(auth_repo=auth_repo, commits=commits)
            }
    else:
        if auth_repo.path in _repositories_dict and all(
            commit in _repositories_dict[auth_repo.path] for commit in commits
        ):
            loaded_repositories_dict = _repositories_dict
        else:
            loaded_repositories_dict = {
                auth_repo.path: _load_repositories(
                    auth_repo=auth_repo,
                    commits=commits,
                    excluded_target_globs=excluded_target_globs,
                    library_dir=library_dir,
                    raise_error_if_no_urls=raise_error_if_no_urls,
                )
            }

    auth_msg = "included authentication " if load_auth else ""
    repositories_msg = (
        "Included authentication repositories" if load_auth else "Repositories"
    )
    taf_logger.debug(
        "Auth repo {}: getting a deduplicated list of {}repositories",
        auth_repo.path,
        auth_msg,
    )
    all_repositories = loaded_repositories_dict.get(auth_repo.path)
    if all_repositories is None:
        taf_logger.debug(
            "{} defined in authentication repository {} have not been loaded",
            repositories_msg,
            auth_repo.path,
        )
        raise RepositoriesNotFoundError(
            f"{repositories_msg} defined in authentication repository"
            f" {auth_repo.path} have not been loaded"
        )
    repositories = {}
    # persuming that the newest commit is the last one
    for commit in commits:
        if commit not in all_repositories:
            taf_logger.debug(
                "{} defined in authentication repository {} at revision {} have "
                "not been loaded",
                repositories_msg,
                auth_repo.path,
                commit,
            )
            raise RepositoriesNotFoundError(
                f"{repositories_msg} defined in authentication repository "
                f"{auth_repo.path} at revision {commit} have not been loaded"
            )
        for name, repo in all_repositories[commit].items():
            # will overwrite older repo with newer
            repositories[name] = repo

    taf_logger.debug(
        "Auth repo {}: deduplicated list of {} repositories {}",
        auth_repo.path,
        auth_msg,
        ", ".join(repositories.keys()),
    )
    return repositories


def get_repository(
    auth_repo: AuthenticationRepository, name: str, commit: Optional[Commitish] = None
) -> Optional[GitRepository]:
    repositories = get_repositories(auth_repo, commit)
    if repositories is None:
        return None
    return repositories.get(name)


def get_auth_repository(
    auth_repo: AuthenticationRepository, name: str, commit: Optional[Commitish] = None
) -> Optional[AuthenticationRepository]:
    repositories = get_auth_repositories(auth_repo, commit)
    if repositories is None:
        return None
    return repositories.get(name)


def get_auth_repositories(
    auth_repo: AuthenticationRepository, commit: Optional[Commitish] = None
) -> Dict[str, AuthenticationRepository]:
    return _get_repositories(auth_repo, commit, True)


def get_repositories(
    auth_repo: AuthenticationRepository, commit: Optional[Commitish] = None
) -> Dict[str, GitRepository]:
    return _get_repositories(auth_repo, commit)


def _get_repositories(
    auth_repo: AuthenticationRepository,
    commit: Optional[Commitish] = None,
    load_auth: Optional[bool] = False,
):
    loaded_repositories_dict = _dependencies_dict if load_auth else _repositories_dict
    auth_msg = "included authentication " if load_auth else ""
    repositories_msg = (
        "Included authentication repositories" if load_auth else "Repositories"
    )
    if commit is None:
        commit = auth_repo.head_commit()
    taf_logger.debug(
        "Auth repo {}: finding {}repositories defined at commit {}",
        auth_repo.path,
        auth_msg,
        commit,
    )
    all_repositories = loaded_repositories_dict.get(auth_repo.path)
    if all_repositories is None:
        taf_logger.error(
            "{} defined in authentication repository {} have not been loaded",
            repositories_msg,
            auth_repo.path,
        )
        raise RepositoriesNotFoundError(
            f"{repositories_msg} defined in authentication repository"
            f" {auth_repo.path} have not been loaded"
        )

    repositories = all_repositories.get(commit)
    if repositories is None:
        taf_logger.debug(
            "{} defined in authentication repository {} at revision {} have "
            "not been loaded",
            repositories_msg,
            auth_repo.path,
            commit,
        )
        raise RepositoriesNotFoundError(
            f"{repositories_msg} defined in authentication repository "
            f"{auth_repo.path} at revision {commit} have not been loaded"
        )
    taf_logger.debug(
        "Auth repo {}: found the following {}repositories at revision {}: {}",
        auth_repo.path,
        auth_msg,
        commit,
        ", ".join(repositories.keys()),
    )
    return repositories


def get_repositories_by_custom_data(
    auth_repo: AuthenticationRepository,
    commit: Optional[Commitish] = None,
    **custom_data,
):
    taf_logger.debug(
        "Auth repo {}: finding repositories by custom data {}",
        auth_repo.path,
        custom_data,
    )
    repositories = get_repositories(auth_repo, commit).values()

    def _compare(repo):
        # Check if `custom` dict is subset of targets[path]['custom'] dict
        try:
            return custom_data.items() <= repo.custom.items()
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


def _initialize_repository(
    factory, repo_classes, urls, custom, library_dir, name, default_branch, auth_repo
):
    git_repo = None

    allow_unsafe = False
    try:
        if factory is not None:
            git_repo = factory(
                library_dir, name, urls, custom, default_branch, allow_unsafe
            )
        else:
            git_repo_class = _determine_repo_class(repo_classes, name)
            git_repo = git_repo_class(
                library_dir, name, urls, custom, default_branch, allow_unsafe
            )
    except Exception as e:
        taf_logger.error(
            "Auth repo {}: an error occurred while instantiating repository {}: {}",
            auth_repo.path,
            name,
            str(e),
        )
        raise RepositoryInstantiationError(Path(library_dir, name), str(e))
    # allows us to partially update repositories
    if git_repo:
        if not isinstance(git_repo, GitRepository):
            raise Exception(f"{type(git_repo)} is not a subclass of GitRepository")
    return git_repo


def load_dependencies_json(
    auth_repo: AuthenticationRepository, commit: Optional[Commitish] = None
) -> Optional[Dict]:
    if commit is None:
        branch = auth_repo.default_branch
        if branch is None:
            raise TAFError(
                "Could not load dependencies. Commit is not specified and default branch could not be determined"
            )
        commit = auth_repo.top_commit_of_branch(branch)
        if commit is None:
            raise TAFError(
                "Could not load dependencies. Commit is not specified and head commit could not be determined"
            )
    try:
        return _get_json_file(auth_repo, DEPENDENCIES_JSON_PATH, commit)
    except InvalidOrMissingMetadataError as e:
        if f"{DEPENDENCIES_JSON_PATH} not available at revision" in str(e):
            taf_logger.debug("Skipping commit {} due to: {}", commit, str(e))
        return None


def load_repositories_json(
    auth_repo: AuthenticationRepository, commit: Optional[Commitish] = None
) -> Optional[Dict]:
    if commit is None:
        branch = auth_repo.default_branch
        if branch is None:
            raise TAFError(
                "Could not load repositories. Commit is not specified and default branch could not be determined"
            )
        commit = auth_repo.top_commit_of_branch(branch)
        if commit is None:
            raise TAFError(
                "Could not load repositories. Commit is not specified and head commit could not be determined"
            )
    try:
        return _get_json_file(auth_repo, REPOSITORIES_JSON_PATH, commit)
    except InvalidOrMissingMetadataError as e:
        if f"{REPOSITORIES_JSON_PATH} not available at revision" in str(e):
            taf_logger.debug("Skipping commit {} due to: {}", commit, str(e))
            return None
        else:
            raise


def load_mirrors_json(
    auth_repo: AuthenticationRepository, commit: Commitish
) -> Optional[Dict]:
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


def _targets_of_roles(
    auth_repo: AuthenticationRepository,
    commit: Commitish,
    roles: Optional[List[str]] = None,
):

    with auth_repo.repository_at_revision(commit):
        return auth_repo.get_signed_targets_with_custom_data(roles)


def repositories_loaded(auth_repo: AuthenticationRepository) -> bool:
    all_repositories = _repositories_dict.get(auth_repo.path)
    if all_repositories is None or not len(all_repositories):
        return False
    return any(
        len(repositories_at_commit)
        for repositories_at_commit in all_repositories.values()
    )


def get_all_auth_repos(
    auth_repo: AuthenticationRepository,
    auth_repos_list: Optional[list] = None,
):
    """
    Recursively iterate through dependencies and add all auth repos to a list.
    """
    if auth_repos_list is None:
        auth_repos_list = []

    # If current repo is not in the list, add it:
    if not any(auth_repo.path == repo.path for repo in auth_repos_list):
        auth_repos_list.append(auth_repo)
    # Load dependencies and iterate recursively:
    load_dependencies(auth_repo)
    auth_repos = list(
        get_deduplicated_auth_repositories(auth_repo, commits=None).values()
    )
    if len(auth_repos) != 0:
        for auth_repo in auth_repos:
            get_all_auth_repos(auth_repo, auth_repos_list)

    return auth_repos_list
