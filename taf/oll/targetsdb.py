from pathlib import Path

from taf.oll.exceptions import TargetsNotFound
from taf.oll.GitRepository import GitRepository

# {
#     'authentication_repo_name': {
#         'commit' : {
#             'target_path1': (target_git_repository1, custom_data1)
#             'target_path2': (target_git_repository2, custom_data2)
#             ...
#         }
#     }
# }

_targetsdb_dict = {}


def load_targets(auth_repo, targets_classes=None, factory=None, root_dir=None, commit=None):
  """
  Creates target repositories by reading the targets.json file at the specified revision,
  given an atuhentication repo. If the commit is not specified, it is set to the HEAD
  of the authentication. It is possible to specify git repository class that will
  be created per target.
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
    commit: Authentication repository's commit at which to read targets.json
  """

  global _targetsdb_dict

  if auth_repo.name not in _targetsdb_dict:
    _targetsdb_dict[auth_repo.name] = {}
  elif commit in _targetsdb_dict[auth_repo.name]:
    return

  if commit is None:
    commit = auth_repo.head_commit_sha()
  if root_dir is None:
    root_dir = Path(auth_repo.repo_path).parent

  targets_dict = {}
  _targetsdb_dict[auth_repo.name][commit] = targets_dict

  targets = auth_repo.get_json(commit, 'metadata/targets.json')
  mirrors = auth_repo.get_json(commit, 'mirrors.json')

  # target repositories are defined in both mirrors.json and targets.json
  repos = [repository['custom']['path']
           for repository in mirrors['signed']['mirrors']]
  for target_path, target_data in targets['signed']['targets'].items():
    if target_path not in repos:
      continue
    custom = target_data.get('custom', None)

    if factory is not None:
      target = factory(root_dir, target_path, custom)
    else:
      target_class = _determine_target_class(targets_classes, target_path)
      target = target_class(root_dir, target_path)

    if not isinstance(target, GitRepository):
      raise Exception(f'{type(target)} is not a subclass of GitRepository')

    targets_dict[target_path] = (target, custom)


def _determine_target_class(targets_classes, path):
  # if no class is specified, return the default one
  if targets_classes is None:
    return GitRepository

  # if only one value is specified, that means that all target repositories
  # should be of the same class
  if not isinstance(targets_classes, dict):
    return targets_classes

  if path in targets_classes:
    return targets_classes[path]

  if 'default' in targets_classes:
    return targets_classes['default']

  return GitRepository


def get_target_paths_by_custom_data(auth_repo, commit=None, **custom):
  if not commit:
    commit = auth_repo.head_commit_sha()
  targets_json = auth_repo.get_json(commit, 'metadata/targets.json')
  targets = targets_json['signed']['targets']

  def _compare(path):
    # Check if `custom` dict is subset of targets[path]['custom'] dict
    try:
      return custom.items() <= targets[path]['custom'].items()
    except (AttributeError, KeyError):
      return False

  return list(filter(_compare, targets)) if custom else list(targets)


def get_targets(auth_repo, commit=None):

  targets_and_custom = get_targets_and_custom(auth_repo, commit)
  return [target for target, _ in targets_and_custom.values()]


def get_target(auth_repo, target_path, commit=None):
  return get_target_and_custom(auth_repo, target_path, commit)[0]


def get_targets_and_custom(auth_repo, commit):
  global _targetsdb_dict

  all_targets = _targetsdb_dict.get(auth_repo.name, None)
  if all_targets is None:
    raise TargetsNotFound(f'Targets of authentication repository {auth_repo.name} ',
                          'have not been loaded')

  if commit is None:
    commit = auth_repo.head_commit_sha()

  targets_and_custom = all_targets.get(commit, None)
  if targets_and_custom is None:
    raise TargetsNotFound(f'Targets of authentication repository {auth_repo.name} '
                          'at revision {commit} have not been loaded')
  return targets_and_custom


def get_target_and_custom(auth_repo, target_path, commit=None):

  targets = get_targets(auth_repo, commit)
  target = targets.get(target_path, None)
  if target is None:
    if commit is not None:
      msg = f'Target {target_path} not defined in {auth_repo.name} at revision {commit}'
    else:
      msg = f'Target {target_path} not defined in {auth_repo.name} at HEAD revision'
    raise TargetsNotFound(msg)
  return target


def get_targets_by_custom_data(auth_repo, commit=None, **custom_data):
  targets = []
  targets_and_custom = get_targets_and_custom(auth_repo, commit)
  for target, custom in targets_and_custom.values():
    for custom_property, custom_value in custom_data.items():
      if custom_property in custom and custom[custom_property] == custom_value:
        targets.append(target)
  if len(targets):
    return targets
  raise TargetsNotFound(
      f'Target associated with custom data {custom_data} not found')
