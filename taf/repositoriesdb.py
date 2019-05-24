import json
from pathlib import Path
from subprocess import CalledProcessError

from taf.exceptions import InvalidOrMissingMetadataError, RepositoriesNotFoundError
from taf.GitRepository import GitRepository

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
repositories_path = 'targets/repositories.json'
targets_path = 'metadata/targets.json'


def load_repositories(auth_repo, repo_classes=None, factory=None,
                      root_dir=None, only_load_targets=False, commits=None):
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
      is found, the class is set to TAF's GitRepository.
      If target_classes is a single class, all targets will be of that type.
      If target_classes is None, all targets will be of TAF's GitRepository type.
    root_dir: root directory relative to which the target paths are specified
    commits: Authentication repository's commits at which to read targets.json
    only_load_targets: specifies if only repositories specified in targets.json should be loaded.
      If set to false, all repositories defined in repositories.json are loaded, regardless of if
      they are targets or not.
  """

  global _repositories_dict
  if auth_repo.name not in _repositories_dict:
    _repositories_dict[auth_repo.name] = {}

  if commits is None:
    commits = [auth_repo.head_commit_sha()]
  if root_dir is None:
    root_dir = Path(auth_repo.repo_path).parent

  for commit in commits:
    repositories_dict = {}
    # check if already loaded
    if commit in _repositories_dict[auth_repo.name]:
      continue

    _repositories_dict[auth_repo.name][commit] = repositories_dict

    try:
      repositories = _get_json_file(auth_repo, repositories_path, commit)
      targets = _get_json_file(auth_repo, targets_path, commit)
    except InvalidOrMissingMetadataError as e:
      print('Skipping commit {}. {}'.format(commit, e))
      continue

    # target repositories are defined in both mirrors.json and targets.json
    repositories = repositories['repositories']
    targets = targets['signed']['targets']
    for path, repo_data in repositories.items():
      urls = repo_data['urls']
      target = targets.get(path)
      if target is None and only_load_targets:
        continue
      additional_info = _get_custom_data(repo_data, targets.get(path))

      if factory is not None:
        git_repo = factory(root_dir, path, urls, additional_info)
      else:
        git_repo_class = _determine_repo_class(repo_classes, path)
        git_repo = git_repo_class(root_dir, path, urls, additional_info)

      if not isinstance(git_repo, GitRepository):
        raise Exception('{} is not a subclass of GitRepository'
                        .format(type(git_repo)))

      repositories_dict[path] = git_repo


def _determine_repo_class(repo_classes, path):
  # if no class is specified, return the default one
  if repo_classes is None:
    return GitRepository

  # if only one value is specified, that means that all target repositories
  # should be of the same class
  if not isinstance(repo_classes, dict):
    return repo_classes

  if path in repo_classes:
    return repo_classes[path]

  if 'default' in repo_classes:
    return repo_classes['default']

  return GitRepository


def _get_custom_data(repo, target):
  custom = repo.get('custom', {})
  target_custom = target.get('custom') if target is not None else None
  if target_custom is not None:
    custom.update(target_custom)
  return custom


def _get_json_file(auth_repo, path, commit):
  try:
    return auth_repo.get_json(commit, path)
  except CalledProcessError:
    raise InvalidOrMissingMetadataError('{} not available at revision {}'
                                        .format(path, commit))
  except json.decoder.JSONDecodeError:
    raise InvalidOrMissingMetadataError('{} not a valid json at revision {}'
                                        .format(path, commit))


def get_repositories_paths_by_custom_data(auth_repo, commit=None, **custom):
  if not commit:
    commit = auth_repo.head_commit_sha()

  targets = auth_repo.get_json(commit, targets_path)
  repositories = auth_repo.get_json(commit, repositories_path)
  repositories = repositories['repositories']
  targets = targets['signed']['targets']

  def _compare(path):
    # Check if `custom` dict is subset of targets[path]['custom'] dict
    try:
      return custom.items() <= _get_custom_data(repositories[path],
                                                targets.get(path)).items()
    except (AttributeError, KeyError):
      return False

  paths = list(filter(_compare, repositories)) if custom else list(repositories)
  if len(paths):
    return paths
  raise RepositoriesNotFoundError('Repositories associated with custom data {} not found'
                                  .format(custom))


def get_deduplicated_repositories(auth_repo, commits):
  global _repositories_dict
  all_repositories = _repositories_dict.get(auth_repo.name)
  if all_repositories is None:
    raise RepositoriesNotFoundError('Repositories defined in authentication repository'
                                    ' {} have not been loaded'.format(auth_repo.name))
  repositories = {}
  # persuming that the newest commit is the last one
  for commit in commits:
    if not commit in all_repositories:
      raise RepositoriesNotFoundError('Repositories defined in authentication repository '
                                      '{} at revision {} have not been loaded'
                                      .format(auth_repo.name, commit))
    for path, repo in all_repositories[commit].items():
      # will overwrite older repo with newer
      repositories[path] = repo

  return repositories


def get_repository(auth_repo, path, commit=None):
  return get_repositories(auth_repo, commit)[path]


def get_repositories(auth_repo, commit):
  global _repositories_dict

  all_repositories = _repositories_dict.get(auth_repo.name)
  if all_repositories is None:
    raise RepositoriesNotFoundError('Repositories defined in authentication repository'
                                    ' {} have not been loaded'.format(auth_repo.name))

  if commit is None:
    commit = auth_repo.head_commit_sha()

  repositories = all_repositories.get(commit)
  if repositories is None:
    raise RepositoriesNotFoundError('Repositories defined in authentication repository '
                                    '{} at revision {} have not been loaded'
                                    .format(auth_repo.name, commit))
  return repositories


def get_repositories_by_custom_data(auth_repo, commit=None, **custom_data):
  repositories = get_repositories(auth_repo, commit).values()

  def _compare(repo):
    # Check if `custom` dict is subset of targets[path]['custom'] dict
    try:
      return custom_data.items() <= repo.additional_info.items()
    except (AttributeError, KeyError):
      return False
  found_repos = list(filter(_compare, repositories)
                     ) if custom_data else list(repositories)

  if len(found_repos):
    return found_repos
  raise RepositoriesNotFoundError('Repositories associated with custom data {} not found'
                                  .format(custom_data))
