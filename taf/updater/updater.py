import os
import traceback
import shutil

import tuf
import tuf.client.updater as tuf_updater
import taf.repositoriesdb as repositoriesdb
from taf.updater.exceptions import UpdateFailed
from taf.updater.handlers import GitUpdater



def update(url, clients_directory, repo_name, targets_dir):
  """
  The general idea is the updater is the following:
  - We have a git repository which contains the metadata files. These metadata files
  are in the 'metadata' directory
  - Clients have a clone of that repository on their local machine and want to update it
  - We don't want to simply pull the updates. We want to verify that the new commits
  (committed after the most recent one in the client's local repository)
  - For each of the new commits, we want to check if all metadata is valid. The set of
  metadata should be valid as a whole at that revision. Not only do we want to make sure
  that a metadata which is supposed to be changed was indeed updated and is valid, but
  also to make sure that if a metadata file should not be updated, it remained the same.
  - We also want to make sure that all targets metadata is valid (including the delegated roles)
  - We do not want to simply update the metadata to the latest version, without skipping
  these checks. We want to check each commit, not just the last one.
  - If we are checking a commit which is not the latest one, we do not want to report an error
  if the metadata expired. We want to make sure that that was valid at the time when the
  metadata was committed.
  - We can rely on the TUF's way of handling metadata, by using the current and previous
  directories. We just want to automatically create and update them. They should not
  remain on the client's machine.
  - We do not want to modify TUF's updater to much, but still need to get around the fact
  that TUF skips mirrors which do not have valid and/or current metadata files. Also, we
  do not simply want to find the latest metadata, we want to validate everything in-between.
  That is why the idea is to call refresh multiple times, until the last commit is reached.
  The 'GitMetadataUpdater' updater is designed in such a way that for each new call it
  loads data from a most recent commit.
  """

  # TODO old HEAD as an input parameter

  clients_repository = os.path.join(clients_directory, repo_name)

  # Setting 'tuf.settings.repository_directory' with the temporary client
  # directory copied from the original repository files.
  tuf.settings.repositories_directory = clients_directory

  repository_mirrors = {'mirror1': {'url_prefix': url,
                                    'metadata_path': 'metadata',
                                    'targets_path': 'targets',
                                    'confined_target_dirs': ['']}}

  repository_updater = tuf_updater.Updater(repo_name,
                                           repository_mirrors,
                                           GitUpdater)

  try:
    while not repository_updater.update_handler.update_done():
      repository_updater.refresh()
      # using refresh, we have updated all main roles
      # we still need to update the delegated roles (if there are any)
      # that is handled by get_current_targets
      current_targets = repository_updater.update_handler.get_current_targets()
      for target_path in current_targets:
        target = repository_updater.get_one_valid_targetinfo(target_path)
        target_filepath = target['filepath']
        trusted_length = target['fileinfo']['length']
        trusted_hashes = target['fileinfo']['hashes']
        repository_updater._get_target_file(target_filepath, trusted_length, trusted_hashes)  # pylint: disable=W0212 # noqa
        print('Successfully validated file {} at {}'
              .format(target_filepath, repository_updater.update_handler.current_commit))

  except Exception as e:
    # for now, useful for debugging
    traceback.print_exc()
    raise UpdateFailed('Failed to update authentication repository {} due to error: {}'
                       .format(clients_directory, e))
  finally:
    repository_updater.update_handler.cleanup()

  # successfully validated the authentication repository, it is safe to pull the changes
  # up until the latest validated commit
  # fetch and merge up until a commit
  users_auth_repo = repository_updater.update_handler.users_auth_repo
  last_commit = repository_updater.update_handler.commits[-1]
  users_auth_repo.clone_or_pull_up_to_commit(last_commit)

 # it is possible that a repository is not specified in all commits of the authentication
  # repository
  # it might have been added a bit later, only appearing in newer commits
  # also, a repository could've been removed
  # TODO what do we want to do with these repositories? TUF removes targets from disk if they
  # are no longer specified in targets.json

  commits = repository_updater.update_handler.commits
  repositoriesdb.load_repositories(users_auth_repo, root_dir=targets_dir, commits=commits)
  repositories = repositoriesdb.get_deduplicated_repositories(users_auth_repo, commits)
  repositories_commits = users_auth_repo.sorted_commits_per_repositories(commits)
  _update_target_repositories(repositories, repositories_commits)

def _update_target_repositories(repositories, repositories_commits):
  cloned_repositories = []
  for path, repository in repositories.items():
    if not repository.is_git_repository():
      old_head = None
    else:
      old_head = repository.head_commit_sha()

    if old_head is None:
      repository.clone(no_checkout=True)
      cloned_repositories.append(repository)
    else:
      repository.fetch(True)

    try:
      _update_target_repository(repository, old_head, repositories_commits[path])
    except UpdateFailed as e:
      # delete all repositories that were cloned
      for repo in cloned_repositories:
        shutil.rmtree(repo.repo_path)
      # TODO is it important to undo a fetch if the repository was not cloned?
      raise e

  print('Succsfully updated target repositories')
  # if update is successful, merge the commits
  for path, repository in repositories.items():
    repository.checkout_branch('master')
    repository.merge_commit(repositories_commits[path][-1])


def _update_target_repository(repository, old_head, target_commits):

    new_commits = repository.all_commits_since_commit(old_head)
    # The repository might not have been protected by TUF from the first
    # commit. If the repository already existed, then the latest commit in that repository
    # should match the first commit in repositories_commits for that repository
    # Also, a new commit might have been pushed after the update process
    # started and before fetch was called
    update_successful = len(new_commits) >= len(target_commits)
    if update_successful:
      for target_commit, repo_commit in zip(target_commits, new_commits):
        if target_commit != repo_commit:
          update_successful = False
          break

    if not update_successful:
      raise UpdateFailed('Mismatch between target commits specified in authentication repository'
                         'and target repository {}'.format(repository.target_path))