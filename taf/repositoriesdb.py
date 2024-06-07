import json
from typing import Callable, Dict, List, Optional, Type
import fnmatch
from pathlib import Path
from tuf.repository_tool import TARGETS_DIRECTORY_NAME
from taf.auth_repo import AuthenticationRepository
from taf.exceptions import (
    InvalidOrMissingMetadataError,
    RepositoriesNotFoundError,
    RepositoryInstantiationError,
    GitError,
    TAFError,
)
from taf.git import GitRepository
from taf.log import taf_logger


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
    auth_repo: AuthenticationRepository, commit: Optional[str] = None
) -> bool:
    if commit is None:
        commit = auth_repo.head_commit_sha()
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
    commits: Optional[List[str]] = None,
) -> None:
    global _dependencies_dict
    if auth_repo.path not in _dependencies_dict:
        _dependencies_dict[auth_repo.path] = {}

    if commits is None:
        auth_repo_head_commit = auth_repo.head_commit_sha()
        if auth_repo_head_commit is None:
            taf_logger.info(
                "Authentication repository does not exist - cannot load included authentication repositories"
            )
            return
        commits = [auth_repo_head_commit]

    taf_logger.debug(
        "Loading {}'s included authentication repositories at revisions {}",
        auth_repo.path,
        ", ".join(commits),
    )

    if library_dir is None:
        library_dir = str(Path(auth_repo.path).parent.parent)

    mirrors = load_mirrors_json(auth_repo, commits[-1])
    for commit in commits:
        dependencies_dict: Dict = {}
        # check if already loaded
        if commit in _dependencies_dict[auth_repo.path]:
            continue

        _dependencies_dict[auth_repo.path][commit] = dependencies_dict

        dependencies = load_dependencies_json(auth_repo, commit)
        if dependencies is None:
            continue

        dependencies = dependencies["dependencies"]
        if dependencies is None:
            continue

        for name, repo_data in dependencies.items():
            try:
                if mirrors:
                    urls = _get_urls(mirrors, name, repo_data)
                else:
                    urls = [name]
            except RepositoryInstantiationError:
                dependencies_dict.clear()
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
            dependencies_dict[name] = contained_auth_repo

        taf_logger.debug(
            "Loaded the following contained authentication repositories at revision {}: {}",
            commit,
            ", ".join(dependencies_dict.keys()),
        )

    # we don't need to set auth_repo dependencies for each commit,
    # just the latest version
    latest_commit = commits[-1]
    dependencies = load_dependencies_json(auth_repo, latest_commit)
    auth_repo.dependencies = (
        dependencies["dependencies"] if dependencies is not None else {}
    )


def load_repositories(
    auth_repo: AuthenticationRepository,
    repo_classes: Optional[Type] = None,
    factory: Optional[Callable] = None,
    library_dir: Optional[str] = None,
    only_load_targets: bool = True,
    commits: Optional[List[str]] = None,
    roles: Optional[List[str]] = None,
    excluded_target_globs: Optional[List[str]] = None,
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
    if auth_repo.path not in _repositories_dict:
        _repositories_dict[auth_repo.path] = {}
    if excluded_target_globs is None:
        excluded_target_globs = []

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

    if library_dir is None:
        library_dir = str(Path(auth_repo.path).parent.parent)

    if roles is not None and len(roles):
        only_load_targets = True

    skipped_targets = []
    mirrors = load_mirrors_json(auth_repo, commits[-1])
    for commit in commits:
        repositories_dict: Dict = {}
        # check if already loaded
        if commit in _repositories_dict[auth_repo.path]:
            continue

        _repositories_dict[auth_repo.path][commit] = repositories_dict

        repositories = load_repositories_json(auth_repo, commit)
        if repositories is None:
            continue

        # target repositories are defined in both repositories.json and targets.json
        repositories = repositories["repositories"]
        if repositories is None:
            continue
        targets = _targets_of_roles(auth_repo, commit, roles)

        for name, repo_data in repositories.items():
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
            urls = _get_urls(mirrors, name, repo_data)
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
                repositories_dict[name] = git_repo

        taf_logger.debug(
            "Loaded the following repositories at revision {}: {}",
            commit,
            ", ".join(repositories_dict.keys()),
        )


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


def _get_json_file(auth_repo, name, commit):
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


def _get_urls(mirrors, repo_name, repo_data=None) -> List[str]:
    if repo_data is not None and "urls" in repo_data:
        return repo_data["urls"]
    elif mirrors is None:
        raise RepositoryInstantiationError(
            repo_name,
            f"{MIRRORS_JSON_PATH} does not exists or is not valid and no urls of {repo_name} specified in {REPOSITORIES_JSON_PATH}",
        )

    try:
        org_name, repo_name = repo_name.split("/")
    except Exception:
        raise RepositoryInstantiationError(
            repo_name, "repository name is not in the org_name/repo_name format"
        )

    return [mirror.format(org_name=org_name, repo_name=repo_name) for mirror in mirrors]


def _get_target_default_branch(
    auth_repo: AuthenticationRepository, name: str, commit: str
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
    auth_repo: AuthenticationRepository, commit: Optional[str] = None, **custom
) -> Optional[List[str]]:
    if not commit:
        commit = auth_repo.head_commit_sha()
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
    auth_repo: AuthenticationRepository, commits: List[str]
) -> Dict[str, AuthenticationRepository]:
    return _get_deduplicated_target_or_auth_repositories(auth_repo, commits, True)


def get_deduplicated_repositories(
    auth_repo: AuthenticationRepository, commits: Optional[List[str]] = None
) -> Dict[str, GitRepository]:
    return _get_deduplicated_target_or_auth_repositories(auth_repo, commits)


def _get_deduplicated_target_or_auth_repositories(auth_repo, commits, load_auth=False):
    if commits is None:
        commits = [auth_repo.head_commit_sha()]

    loaded_repositories_dict = _dependencies_dict if load_auth else _repositories_dict
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
        taf_logger.error(
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
            taf_logger.error(
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
        "Auth repo {}: deduplicated list of {}repositories {}",
        auth_repo.path,
        auth_msg,
        ", ".join(repositories.keys()),
    )
    return repositories


def get_repository(
    auth_repo: AuthenticationRepository, name: str, commit: Optional[str] = None
) -> Optional[GitRepository]:
    repositories = get_repositories(auth_repo, commit)
    if repositories is None:
        return None
    return repositories.get(name)


def get_auth_repository(
    auth_repo: AuthenticationRepository, name: str, commit: Optional[str] = None
) -> Optional[AuthenticationRepository]:
    repositories = get_auth_repositories(auth_repo, commit)
    if repositories is None:
        return None
    return repositories.get(name)


def get_auth_repositories(
    auth_repo: AuthenticationRepository, commit: Optional[str] = None
) -> Dict[str, AuthenticationRepository]:
    return _get_repositories(auth_repo, commit, True)


def get_repositories(
    auth_repo: AuthenticationRepository, commit: Optional[str] = None
) -> Dict[str, GitRepository]:
    return _get_repositories(auth_repo, commit)


def _get_repositories(auth_repo, commit=None, load_auth=False):
    loaded_repositories_dict = _dependencies_dict if load_auth else _repositories_dict
    auth_msg = "included authentication " if load_auth else ""
    repositories_msg = (
        "Included authentication repositories" if load_auth else "Repositories"
    )
    if commit is None:
        commit = auth_repo.head_commit_sha()
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
        taf_logger.error(
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
    auth_repo: AuthenticationRepository, commit: Optional[str] = None, **custom_data
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
    auth_repo: AuthenticationRepository, commit: Optional[str] = None
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
    auth_repo: AuthenticationRepository, commit: Optional[str] = None
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
    auth_repo: AuthenticationRepository, commit: str
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


def _targets_of_roles(auth_repo, commit, roles=None):

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
