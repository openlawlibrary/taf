import os
import json
from .utils import run



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
