import json
from collections import defaultdict
from subprocess import CalledProcessError

from taf.GitRepository import GitRepository


class AuthenticationRepo(GitRepository):

  def __init__(self, root_dir, metadata_path, targets_path, target_path=None,
               repo_urls=None, additional_info=None, bare=False):
    super().__init__(root_dir, target_path, repo_urls, additional_info, bare)
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
    return repositories_commits

  def target_commits_at_revisions(self, commits):
    targets = defaultdict(dict)
    for commit in commits:
      try:
        targets_at_revision = \
            self.get_json(commit, self.metadata_path + '/targets.json')['signed']['targets']
        repositories_at_revision = \
            self.get_json(commit, self.targets_path + '/repositories.json')['repositories']
        for target_path in targets_at_revision:
          try:
            if target_path not in repositories_at_revision:
              # we only care about repositories
              continue
            target_commit = \
                self.get_json(commit, self.targets_path + '/' + target_path).get('commit')
            targets[commit][target_path] = target_commit
          except json.decoder.JSONDecodeError:
            print('Target file {} is not a valid json at revision.  {}'.format(target_path, commit))
            continue
      except CalledProcessError:
        # if there is a commit without targets.json (e.g. the initial commit)
        # this error will occur
        continue
      except json.decoder.JSONDecodeError:
        continue
    return targets
