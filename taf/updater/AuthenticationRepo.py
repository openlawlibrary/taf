import json
import os
import taf.log
from collections import defaultdict
from subprocess import CalledProcessError

from taf.GitRepository import GitRepository

logger = taf.log.get_logger(__name__)


class AuthenticationRepo(GitRepository):

  def __init__(self, root_dir, metadata_path, targets_path, repo_name=None,
               repo_urls=None, additional_info=None, bare=False):
    super().__init__(root_dir, repo_name, repo_urls, additional_info, bare)
    self.targets_path = targets_path
    self.metadata_path = metadata_path

  def sorted_commits_per_repositories(self, commits):
    """Create a list of of subsequent commits per repository
    keeping in mind that targets metadata file is not updated
    everytime something is committed to the authentication repo
    """
    repositories_commits = defaultdict(list)
    targets = self.target_commits_at_revisions(commits)
    previous_commits = {}
    for commit in commits:
      for target_path, target_commit in targets[commit].items():
        previous_commit = previous_commits.get(target_path)
        if previous_commit is None or target_commit != previous_commit:
          repositories_commits[target_path].append(target_commit)
        previous_commits[target_path] = target_commit
    logger.debug('Auth repo %s: new commits per repositories accoring to targets.json: %s',
                 self.repo_name, repositories_commits)
    return repositories_commits

  def target_commits_at_revisions(self, commits):
    targets = defaultdict(dict)
    for commit in commits:
      targets_at_revision = self._safely_get_json(commit, self.metadata_path + '/targets.json')
      if targets_at_revision is None:
        continue
      targets_at_revision = targets_at_revision['signed']['targets']

      repositories_at_revision = self._safely_get_json(commit,
                                                       self.targets_path + '/repositories.json')
      if repositories_at_revision is None:
        continue
      repositories_at_revision = repositories_at_revision['repositories']

      for target_path in targets_at_revision:
        if target_path not in repositories_at_revision:
          # we only care about repositories
          continue
        try:
          target_commit = \
              self.get_json(commit, self.targets_path + '/' + target_path).get('commit')
          targets[commit][target_path] = target_commit
        except json.decoder.JSONDecodeError:
          logger.debug('Auth repo %s: target file %s is not a valid json at revision %s',
                      self.repo_name, target_path, commit)
          continue
    return targets


  def _safely_get_json(self, commit, path):
    try:
      return self.get_json(commit, path)
    except CalledProcessError:
      logger.info('Auth repo %s: %s not available at revision %s', self.repo_name,
                  os.path.basename(path), commit)
    except json.decoder.JSONDecodeError:
      logger.info('Auth repo %s: %s not a valid json at revision %s', self.repo_name,
                  os.path.basename(path), commit)
