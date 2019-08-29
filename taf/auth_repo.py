import json
import os
import taf.log
from collections import defaultdict
from subprocess import CalledProcessError
from pathlib import Path
from taf.git import GitRepository, NamedGitRepository

logger = taf.log.get_logger(__name__)



class AuthRepoMixin(object):


  LAST_VALIDATED_FILENAME = 'last_validated_commit'

  @property
  def conf_dir(self):
    """
    Returns location of the directory which stores the authentication repository's
    configuration files. That is, the last validated commit.
    Create the directory if it does not exist.
    """
    # the repository's name consists of the namespace and name (namespace/name)
    # the configuration directory should be _name
    last_dir = os.path.basename(os.path.normpath(self.repo_path))
    conf_path = os.path.join(os.path.dirname(self.repo_path), '_{}'.format(last_dir))
    if not os.path.exists(conf_path):
      os.makedirs(conf_path)
    return conf_path

  @property
  def certs_dir(self):
    certs_dir = os.path.join(self.repo_path, 'certs')
    if not os.path.exists(certs_dir):
      os.makedirs(certs_dir)
    return certs_dir

  @property
  def last_validated_commit(self):
    """
    Return the last validated commit of the authentication repository
    """
    path = os.path.join(self.conf_dir, self.LAST_VALIDATED_FILENAME)
    try:
      with open(path) as f:
        return f.read()
    except FileNotFoundError:
      return None


  def get_target(self, target_name, commit=None, safely=True):
    if commit is None:
      commit = self.head_commit_sha()
    target_path = (Path(self.targets_path) / target_name).as_posix()
    if safely:
      return self._safely_get_json(commit, target_path)
    else:
      return  self.get_json(commit, target_path)


  def set_last_validated_commit(self, commit):
    """
    Set the last validated commit of the authentication repository
    """
    path = os.path.join(self.conf_dir, self.LAST_VALIDATED_FILENAME)
    logger.debug('Auth repo %s: setting last validated commit to: %s',
                 self.repo_name, commit)
    with open(path, 'w') as f:
      f.write(commit)

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
    logger.debug('Auth repo %s: new commits per repositories according to targets.json: %s',
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




class AuthenticationRepo(AuthRepoMixin, GitRepository):

  def __init__(self, repo_path, metadata_path='metadata', targets_path='targets', repo_urls=None,
               additional_info=None, default_branch='master'):
    super().__init__(repo_path, repo_urls, additional_info, default_branch)
    self.targets_path = targets_path
    self.metadata_path = metadata_path


class NamedAuthenticationRepo(AuthRepoMixin, NamedGitRepository):

  def __init__(self, root_dir, repo_name, metadata_path='metadata', targets_path='targets',
               repo_urls=None, additional_info=None, default_branch='master'):

    super().__init__(root_dir, repo_name, repo_urls, additional_info,
                     default_branch)
    self.targets_path = targets_path
    self.metadata_path = metadata_path
