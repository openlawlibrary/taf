import os
from taf.oll.GitRepository import GitRepository
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

def create_targets(auth_repo, targets_class=None, base_dir=None, commit=None):

  global _targetsdb_dict

  if targets_class is None:
    target_class = GitRepository
  if not issubclass(target_class, GitRepository):
    raise Exception(f'{target_class} is not a subclass of GitRepository')

  if auth_repo.name not in _targetsdb_dict:
    _targetsdb_dict[auth_repo.name] = {}
  elif commit in _targetsdb_dict[auth_repo.name]:
    return

  if commit is None:
    commit = auth_repo.head_commit_sha()
  if base_dir is None:
    base_dir = Path(auth_repo.repo_path).parent

  targets_dict = {}
  _targetsdb_dict[auth_repo.name][commit] = targets_dict

  targets = auth_repo.get_json(commit, 'metadata/targets.json')
  mirrors = auth_repo.get_json(commit, 'mirrors.json')

  # target repositories are defined in both mirrors.json and targets.json
  repos = [repository['custom']['path'] for repository in mirrors['signed']['mirrors']]
  for target_path in targets['signed']['targets']:
    if target_path not in repos:
      continue
    repo_path = os.path.join(base_dir, target_path)
    targets_dict[target_path] = target_class(repo_path)

  return targets_dict

def get_targets(auth_repo, commit=None):

  global _targetsdb_dict

  all_targets = _targetsdb_dict[auth_repo.name]
  if commit is not None:
    return all_targets[commit]
  elif len(all_targets) == 1:
    return all_targets.values()[0]
  else:
    commit = auth_repo.hed_commit_sha()
    return all_commits[commit]
