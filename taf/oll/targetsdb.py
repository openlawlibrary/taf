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

def create_targets(auth_repo, targets_class=None, root_dir=None, commit=None):

  global _targetsdb_dict

  if targets_class is None:
    targets_class = GitRepository
  if not issubclass(targets_class, GitRepository):
    raise Exception(f'{targets_class} is not a subclass of GitRepository')

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
    targets_dict[target_path] = targets_class(root_dir, target_path)

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
