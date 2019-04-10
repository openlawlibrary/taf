import os
import subprocess
import json
from pathlib import Path


class GitRepository(object):

  def __init__(self, repo_path):
    self.repo_path = repo_path

  @property
  def name(self):
    return os.path.basename(self.repo_path)

  def _git(self, cmd):
    return run(f'git -C {self.repo_path} {cmd}')

  def commits_on_branch_and_not_other(self, branch1, branch2, include_branching_commit=False):
    """
    Meant to find commits belonging to a branch which branches off of
    a commit from another branch. For example, to find only commits
    on a speculative branch and not on the master branch.
    """

    commits = self._git(f'log {branch1} --not {branch2} --no-merges --format=format:%H')
    commits = commits.split('\n') if commits else []
    if include_branching_commit:
        branching_commit = self._git(f'rev-list -n 1 {commits[-1]}~1')
        commits.append(branching_commit)

    return commits

  def get_json(self, commit, path):
    s = self.get_file(commit, path)
    return json.loads(s)

  def get_file(self, commit, path):
    return self._git(f'show {commit}:{path}')

  def head_commit_sha(self):
    """Finds sha of the commit to which the current HEAD points"""
    return self._git('rev-parse HEAD')


class TargetRepository(GitRepository):

  def __init__(self, repo_path, target_path):
    super.__init__(repo_path)
    self.target_path = target_path

class AuthenticationRepository(GitRepository):

  def __init__(self, tuf_repository, repo_path, library_dir=None):
    super.__init__(repo_path)
    self.tuf_repository = tuf_repository
    if library_dir is not None:
      self.library_dir = library_dir
    else:
      self.library_dir = str(Path(repo_path).parent)

  @property
  def targets_path(self):
    return os.path.join(self.repository_path, 'targets')

  @property
  def metadata_path(self):
    return os.path.join(self.repository_path, 'metadata')

  @property
  def metadata_staged_path(self):
    return os.path.join(self.repository_path, 'metadata.staged')

  def add_targets(self, paths_and_commits, targets_role='targets'):
    """
    Creates a target .json file containing a repository's commit for each
    repository. Adds those files to the tuf repostiory. Aslo removes
    all targets from the filesystem if the their path is not among the
    provided ones. TUF does not delete targets automatically.
    Args:
      paths_and_commits: a dictionary whose keys are full paths repositories
      (as specified in targets.json, but without the targets directory) and
      whose values are commits which will be stored in target files
      targets_role: a targets role (the root targets role, or one of the delegated ones)
    """
    # delete files if they they no longer correspond to a target defined
    # in targets metadata
    for root, dirs, files in os.walk(self.targets_path):
      for filename in files:
        filepath = os.path.join(root, filename)
        # remove the extension
        filepath, _ = os.path.splitext(filepath)
        if not filepath in paths_and_commits:
          os.remove(filepath)

    targets = self._role_obj(targets_role)
    for path, commit in paths_and_commits.items():
      target_path = os.path.join(self.targets_path, path)
      if not os.path.exists(os.path.dirname(target_path)):
        os.makedirs(os.path.dirname(target_path))
      with open(target_path, 'w') as f:
        json.dump({'commit': commit}, f, indent=4)

      targets.add_target(target_path)

  def _role_obj(self, role):
    """
    A helper function which returns tuf's role object, given the role's name
    args:
      repository: a tuf repository
      role: a role (either one of tuf's root roles, or a delegated target name
   """
    if role == 'targets':
      return self.repository.targets
    elif role == 'snapshot':
      return self.repository.snapshot
    elif role == 'timestamp':
      return self.repository.timestamp
    elif role == 'root':
      return self.repository.root
    return self.repository.targets(role)

  def set_capstone(self, capstone, targets_role='targets'):
    """
    Creates or removes a capstone file, depending on the value of the
    capstone parameter
    Args:
      repository: tuf repository
      capstone: indicator if capstone should be added or removed
      targets_role: a targets role (the root targets role, or one of the delegated ones)
    """
    path = os.path.join(self.targets_path, 'capstone')

    if capstone:
      Path(path).touch()
      self._role_obj(targets_role).add_target('capstone')
    else:
      if os.path.isfile(path):
        os.remove(path)

  def target_repositories(self, commits=None):
    """
    Returns a dictionary containing mappings of target paths
    and the target GitRepository objects, given targets
    defined in targets.json at the provided revisions. If
    the commits are not provided, the HEAD commit's targets.json
    is read
    Args:
      commits: revisions at which to load targets.json in order to
      extract information about target repositories
    """
    targets = {}
    if commits is None:
      commits = [self.head_commit_sha]
    for commit in commits:
      targets = self.get_json('metadata/targets.json')
      for target_path in targets['signed']['targets']:
        if target_path == 'capstone' or target_path in targets:
          continue
        repo_path = os.path.join(self.library_dir, target_path)
        targets[target_path] = TargetRepository(repo_path, target_path)
    return targets.values()

  def write_roles_metadata(self, role, keystore):
    """
    Generates metadata of just one metadata file, corresponding
    to the provided role
    args:
      repository: a tu repository
      role: a tuf role
      keystore: location of the keystore file
    """
    private_role_key = load_role_key(role, keystore)
    self._role_obj(role).load_signing_key(private_role_key)
    # only write this role's metadata
    self.repository.write(role)


def run(*command, **kwargs):
  """Run a command and return its output"""
  if len(command) == 1 and isinstance(command[0], str):
    command = command[0].split()
  print(*command)
  command = [word.format(**os.environ) for word in command]
  try:
    options = dict(stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=True,
                   universal_newlines=True)
    options.update(kwargs)
    completed = subprocess.run(command, **options)
  except subprocess.CalledProcessError as err:
    if err.stdout:
      print(err.stdout)
    if err.stderr:
      print(err.stderr)
    print('Command "{}" returned non-zero exit status {}'.format(' '.join(command),
                                                                 err.returncode))
    raise err
  if completed.stdout:
    print(completed.stdout)
  return completed.stdout.rstrip() if completed.returncode == 0 else None
