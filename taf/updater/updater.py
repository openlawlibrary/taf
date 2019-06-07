
import json
import shutil
import traceback
import tuf
import os
import tuf.client.updater as tuf_updater
import taf.repositoriesdb as repositoriesdb
import taf.settings as settings
import taf.log
from subprocess import CalledProcessError
from collections import defaultdict
from taf.exceptions import UpdateFailedError
from taf.updater.handlers import GitUpdater

logger = taf.log.get_logger(__name__)

def update_repository(url, clients_repo_path, targets_dir, update_from_filesystem):
  """
  <Arguments>
   url:
    URL of the remote authentication repository
   clients_repo_path:
    Client's authentication repository's full path
   targets_dir:
    Directory where the target repositories are located
   update_from_filesystem:
    A flag which indicates if the URL is acutally a file system path
  """
  # if the repository's name is not provided, divide it in parent directory
  # and repository name, since TUF's updater expects a name
  # but set the validate_repo_name setting to False
  clients_dir, repo_name = os.path.split(os.path.normpath(clients_repo_path))
  settings.validate_repo_name = False
  update_named_repository(url, clients_dir, repo_name, targets_dir,
                          update_from_filesystem)

def update_named_repository(url, clients_directory, repo_name, targets_dir,
                            update_from_filesystem):
  """
   <Arguments>
    url:
      URL of the remote authentication repository
    clients_directory:
      Directory where the client's authentication repository is located
    repo_name:
      Name of the authentication repository. Can be namespace prefixed
    targets_dir:
      Directory where the target repositories are located
    update_from_filesystem:
      A flag which indicates if the URL is acutally a file system path

  The general idea of the updater is the following:
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
  # at the moment, we assume that the initial commit is valid and that it contains at least root.json

  settings.update_from_filesystem = update_from_filesystem
  # instantiate TUF's updater
  repository_mirrors = {'mirror1': {'url_prefix': url,
                                    'metadata_path': 'metadata',
                                    'targets_path': 'targets',
                                    'confined_target_dirs': ['']}}

  tuf.settings.repositories_directory = clients_directory
  repository_updater = tuf_updater.Updater(repo_name,
                                           repository_mirrors,
                                           GitUpdater)

  # validate the authentication repository and fetch new commits
  _update_authentication_repository(repository_updater)

  # get target repositories and their commits, as specified in targets.json
  users_auth_repo = repository_updater.update_handler.users_auth_repo
  commits = repository_updater.update_handler.commits
  repositoriesdb.load_repositories(users_auth_repo, root_dir=targets_dir, commits=commits)
  repositories = repositoriesdb.get_deduplicated_repositories(users_auth_repo, commits)
  repositories_commits = users_auth_repo.sorted_commits_per_repositories(commits)

  # update target repositories
  _update_target_repositories(repositories, repositories_commits)

  last_commit = commits[-1]
  logger.info('Merging commit %s into %s', last_commit, users_auth_repo.repo_name)
  # if there were no errors, merge the last validated authentication repository commit
  users_auth_repo.merge_commit(last_commit)
  users_auth_repo.checkout_branch('master')
  # update the last validated commit
  users_auth_repo.set_last_validated_commit(last_commit)


def _update_authentication_repository(repository_updater):

  users_auth_repo = repository_updater.update_handler.users_auth_repo
  logger.info('Validating authentication repository %s', users_auth_repo.repo_name)
  try:
    while not repository_updater.update_handler.update_done():
      current_commit = repository_updater.update_handler.current_commit
      repository_updater.refresh()
      # using refresh, we have updated all main roles
      # we still need to update the delegated roles (if there are any)
      # that is handled by get_current_targets
      current_targets = repository_updater.update_handler.get_current_targets()
      logger.debug('Validated metadata files at revision %s', current_commit)
      for target_path in current_targets:
        target = repository_updater.get_one_valid_targetinfo(target_path)
        target_filepath = target['filepath']
        trusted_length = target['fileinfo']['length']
        trusted_hashes = target['fileinfo']['hashes']
        try:
          repository_updater._get_target_file(target_filepath, trusted_length, trusted_hashes)  # pylint: disable=W0212 # noqa
        except tuf.exceptions.NoWorkingMirrorError as e:
          logger.error('Could not validate file %s', target_filepath)
          raise e
        logger.debug('Successfully validated target file %s at %s', target_filepath,
                     current_commit)
  except Exception as e:
    # for now, useful for debugging
    logger.error('Validation of authentication repository %s failed due to error %s',
                 users_auth_repo.repo_name,  e)
    raise UpdateFailedError('Validation of authentication repository {} due to error: {}'
                            .format(users_auth_repo.repo_name, e))
  finally:
    repository_updater.update_handler.cleanup()

  logger.info('Successfully validated authentication repository %s', users_auth_repo.repo_name)
  # fetch the latest commit or clone the repository without checkout
  # do not merge before targets are validated as well
  if users_auth_repo.is_git_repository:
    users_auth_repo.fetch(True)
  else:
    users_auth_repo.clone(no_checkout=True)


def _update_target_repositories(repositories, repositories_commits):
  logger.info('Validating target repositories')
  # keep track of the repositories which were cloned
  # so that they can be removed if the update fails
  cloned_repositories = []
  for path, repository in repositories.items():
    if not repository.is_git_repository:
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
    except UpdateFailedError as e:
      # delete all repositories that were cloned
      for repo in cloned_repositories:
        logger.debug('Removing cloned repository %s', repo.repo_path)
        shutil.rmtree(repo.repo_path)
      # TODO is it important to undo a fetch if the repository was not cloned?
      raise e

  logger.info('Successfully validated all target repositories.')
  # if update is successful, merge the commits
  for path, repository in repositories.items():
    repository.checkout_branch('master')
    if len(repositories_commits[path]):
      logger.info('Merging %s into %s', repositories_commits[path][-1], repository.repo_name)
      repository.merge_commit(repositories_commits[path][-1])


def _update_target_repository(repository, old_head, target_commits):

  logger.info('Validating target repository %s', repository.repo_name)
  if old_head is not None:
    new_commits = repository.all_fetched_commits()
    new_commits.insert(0, old_head)
  else:
    new_commits = repository.all_commits_since_commit(old_head)
  # A new commit might have been pushed after the update process
  # started and before fetch was called
  # So, the number of new commits, pushed to the target repository, could
  # be greater than the number of these commits according to the authentication
  # repository. The opposite cannot be the case.
  update_successful = len(new_commits) >= len(target_commits)
  if update_successful:
    for target_commit, repo_commit in zip(target_commits, new_commits):
      if target_commit != repo_commit:
        update_successful = False
        break

  if not update_successful:
    logger.error('Mismatch between target commits specified in authentication repository and the '
                 'target repository %s', repository.repo_name)
    raise UpdateFailedError('Mismatch between target commits specified in authentication repository'
                            ' and target repository {}'.format(repository.repo_name))
  logger.info('Successfully validated %s', repository.repo_name)
