import os
from taf.oll.GitRepository import GitRepository
from taf.oll.exceptions import TargetsNotFound
from pathlib import Path

# {
#     'authentication_repo_name': {
#         'commit' : {
#             'target_path1': target_git_repository1,
#             'target_path2': target_git_repository2
#             ...
#         }
#     }
# }

_targetsdb_dict = {}

def create_targets(auth_repo, targets_classes=None, root_dir=None, commit=None):
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

  all_targets_class = targets_classes if not isinstance(targets_classes, dict) else None
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
  repos = [repository['custom']['path'] for repository in mirrors['signed']['mirrors']]
  for target_path in targets['signed']['targets']:
    if target_path not in repos:
      continue

    if all_targets_class:
      target_class = all_targets_class
    else:
      target_class = targets_classes.get(target_path, None)
      if not target_class:
        target_class = targets_classes.get('default', None)

      if not target_class:
        target_class = GitRepository

    if not issubclass(target_class, GitRepository):
        raise Exception(f'{target_class} is not a subclass of GitRepository')

    targets_dict[target_path] = target_class(root_dir, target_path)

def get_targets(auth_repo, commit=None):

  global _targetsdb_dict

  all_targets = _targetsdb_dict.get(auth_repo.name, None)
  if all_targets is None:
    raise TargetsNotFound(f'Targets of authentication repository {auth_repo.name} ',
                          'have not been loaded')

  if commit is None:
    commit = auth_repo.head_commit_sha()

  targets = all_targets.get(commit, None)
  if targets is None:
    raise TargetsNotFound(f'Targets of authentication repository {auth_repo.name} '
                          'at revision {commit} have not been loaded')
  return targets

def get_target(auth_repo, target_path, commit=None):
  targets = get_targets(auth_repo, commit)
  target = targets.get(target_path, None)
  if target is None:
    if commit is not None:
      msg = f'Target {target_path} not defined in {auth_repo.name} at revision {commit}'
    else:
      msg = f'Target {target_path} not defined in {auth_repo.name} at HEAD revision'
    raise TargetsNotFound(msg)

  return target
