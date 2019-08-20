import os
import shutil

import tuf
import tuf.client.updater as tuf_updater

import taf.log
import taf.repositoriesdb as repositoriesdb
import taf.settings as settings
from taf.exceptions import UpdateFailedError
from taf.updater.handlers import GitUpdater
from taf.utils import on_rm_error

logger = taf.log.get_logger(__name__)


def update_repository(url, clients_repo_path, targets_dir, update_from_filesystem,
                      authenticate_test_repo=False, target_repo_classes=None, target_factory=None):
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
   authenticate_test_repo:
    A flag which indicates that the repository to be updated is a test repository
   target_repo_classes:
    A class or a dictionary used when instantiating target repositories.
    See repositoriesdb load_repositories for more details.
   target_factory:
    A git repositories factory used when instantiating target repositories.
    See repositoriesdb load_repositories for more details.
  """
  # if the repository's name is not provided, divide it in parent directory
  # and repository name, since TUF's updater expects a name
  # but set the validate_repo_name setting to False
  clients_dir, repo_name = os.path.split(os.path.normpath(clients_repo_path))
  settings.validate_repo_name = False
  update_named_repository(url, clients_dir, repo_name, targets_dir,
                          update_from_filesystem, authenticate_test_repo,
                          target_repo_classes, target_factory)


def update_named_repository(url, clients_directory, repo_name, targets_dir,
                            update_from_filesystem, authenticate_test_repo=False,
                            target_repo_classes=None, target_factory=None):
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
    authenticate_test_repo:
      A flag which indicates that the repository to be updated is a test repository
    target_repo_classes:
      A class or a dictionary used when instantiating target repositories.
      See repositoriesdb load_repositories for more details.
    target_factory:
      A git repositories factory used when instantiating target repositories.
      See repositoriesdb load_repositories for more details.

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
  users_auth_repo = repository_updater.update_handler.users_auth_repo
  existing_repo = users_auth_repo.is_git_repository_root
  try:
    validation_auth_repo = repository_updater.update_handler.validation_auth_repo
    commits = repository_updater.update_handler.commits
    last_validated_commit = users_auth_repo.last_validated_commit
    if last_validated_commit is None:
      # check if the repository being updated is a test repository
      targets = validation_auth_repo.get_json(commits[-1], 'metadata/targets.json')
      test_repo = 'test-auth-repo' in targets['signed']['targets']
      if test_repo and not authenticate_test_repo:
        raise UpdateFailedError('Repository {} is a test repository. Call update with '
                                '"--authenticate-test-repo" to update a test '
                                'repository'.format(users_auth_repo.repo_name))
      elif not test_repo and authenticate_test_repo:
        raise UpdateFailedError('Repository {} is not a test repository, but update was called '
                                'with the "--authenticate-test-repo" flag'.format(users_auth_repo.repo_name))

    # validate the authentication repository and fetch new commits
    _update_authentication_repository(repository_updater)

    # get target repositories and their commits, as specified in targets.json

    repositoriesdb.load_repositories(users_auth_repo, repo_classes=target_repo_classes,
                                     factory=target_factory, root_dir=targets_dir,
                                     commits=commits)
    repositories = repositoriesdb.get_deduplicated_repositories(users_auth_repo, commits)
    repositories_commits = users_auth_repo.sorted_commits_per_repositories(commits)

    # update target repositories
    repositories_json = users_auth_repo.get_json(commits[-1], 'targets/repositories.json')
    last_validated_commit = users_auth_repo.last_validated_commit
    _update_target_repositories(repositories, repositories_json, repositories_commits,
                                last_validated_commit)

    last_commit = commits[-1]
    logger.info('Merging commit %s into %s', last_commit, users_auth_repo.repo_name)
    # if there were no errors, merge the last validated authentication repository commit
    users_auth_repo.checkout_branch(users_auth_repo.default_branch)
    users_auth_repo.merge_commit(last_commit)
    # update the last validated commit
    users_auth_repo.set_last_validated_commit(last_commit)
  except Exception as e:
    if not existing_repo:
      shutil.rmtree(users_auth_repo.repo_path, onerror=on_rm_error)
      shutil.rmtree(users_auth_repo.conf_dir)
    raise e
  finally:
    repositoriesdb.clear_repositories_db()


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
    raise UpdateFailedError('Validation of authentication repository {} failed due to error: {}'
                            .format(users_auth_repo.repo_name, e))
  finally:
    repository_updater.update_handler.cleanup()

  logger.info('Successfully validated authentication repository %s', users_auth_repo.repo_name)
  # fetch the latest commit or clone the repository without checkout
  # do not merge before targets are validated as well
  if users_auth_repo.is_git_repository_root:
    users_auth_repo.fetch(True)
  else:
    users_auth_repo.clone(no_checkout=True)


def _update_target_repositories(repositories, repositories_json, repositories_commits,
                                last_validated_commit):
  logger.info('Validating target repositories')

  # keep track of the repositories which were cloned
  # so that they can be removed if the update fails
  cloned_repositories = []
  allow_unauthenticated = {}
  new_commits = {}

  for path, repository in repositories.items():

    allow_unauthenticated_for_repo = repositories_json['repositories'][repository.repo_name]. \
        get('custom', {}).get('allow-unauthenticated-commits', False)
    allow_unauthenticated[path] = allow_unauthenticated_for_repo

    # if last_validated_commit is None, start the update from the beginning

    is_git_repository = repository.is_git_repository_root
    if last_validated_commit is None or not is_git_repository:
      old_head = None
    else:
      old_head = repository.head_commit_sha()

    if old_head is None and not is_git_repository:
      repository.clone(no_checkout=True)
      cloned_repositories.append(repository)
    else:
      repository.fetch(True)

    if old_head is not None:
      if allow_unauthenticated:
        old_head = repositories_commits[path][0]
      new_commits_for_repo = repository.all_fetched_commits()
      new_commits_for_repo.insert(0, old_head)
    else:
      new_commits_for_repo = repository.all_commits_since_commit(old_head)
      if is_git_repository:
        # this happens in the case when last_validated_commit does not exist
        # we want to validate all commits, so combine existing commits and
        # fetched commits
        fetched_commits = repository.all_fetched_commits()
        new_commits_for_repo.extend(fetched_commits)
    new_commits[path] = new_commits_for_repo

    try:
      _update_target_repository(repository, new_commits_for_repo, repositories_commits[path],
                                allow_unauthenticated_for_repo)
    except UpdateFailedError as e:
      # delete all repositories that were cloned
      for repo in cloned_repositories:
        logger.debug('Removing cloned repository %s', repo.repo_path)
        shutil.rmtree(repo.repo_path, onerror=on_rm_error)
      # TODO is it important to undo a fetch if the repository was not cloned?
      raise e

  logger.info('Successfully validated all target repositories.')
  # if update is successful, merge the commits
  for path, repository in repositories.items():
    repository.checkout_branch(repository.default_branch)
    if len(repositories_commits[path]):
      logger.info('Merging %s into %s', repositories_commits[path][-1], repository.repo_name)
      last_validated_commit = repositories_commits[path][-1]
      commit_to_merge = last_validated_commit if not allow_unauthenticated[path] else new_commits[path][-1]
      repository.merge_commit(commit_to_merge)
      if not allow_unauthenticated[path]:
        repository.checkout_commit(commit_to_merge)
      else:
        repository.checkout_branch(repository.default_branch)


def _update_target_repository(repository, new_commits, target_commits,
                              allow_unauthenticated):

  logger.info('Validating target repository %s', repository.repo_name)
  # A new commit might have been pushed after the update process
  # started and before fetch was called
  # So, the number of new commits, pushed to the target repository, could
  # be greater than the number of these commits according to the authentication
  # repository. The opposite cannot be the case.
  # In general, if there are additional commits in the target repositories,
  # the updater will finish the update successfully, but will only update the
  # target repositories until the latest validate commit
  if not allow_unauthenticated:
    update_successful = len(new_commits) >= len(target_commits)
    if update_successful:
      for target_commit, repo_commit in zip(target_commits, new_commits):
        if target_commit != repo_commit:
          update_successful = False
          break
    if len(new_commits) > len(target_commits):
      additional_commits = new_commits[len(target_commits):]
      logger.warning('Found commits %s in repository %s that are not accounted for in the authentication repo.'
                     'Repoisitory will be updated up to commit %s', additional_commits,  repository.repo_name,
                     target_commits[-1])
  else:
    logger.info('Unauthenticated commits allowed in repository %s', repository.repo_name)
    update_successful = True
    target_commits_index = 0
    for commit in new_commits:
      if commit in target_commits:
        if commit != target_commits[target_commits_index]:
          update_successful = False
          break
        else:
          target_commits_index += 1

    update_successful = target_commits_index == len(target_commits)

  if not update_successful:
    logger.error('Mismatch between target commits specified in authentication repository and the '
                 'target repository %s', repository.repo_name)
    raise UpdateFailedError('Mismatch between target commits specified in authentication repository'
                            ' and target repository {}'.format(repository.repo_name))
  logger.info('Successfully validated %s', repository.repo_name)
