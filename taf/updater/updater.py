from tuf.repository_tool import *
import os
import time
import shutil
import copy
import tempfile
import logging
import random
import subprocess
import sys
import errno
import unittest
import traceback

import tuf
import tuf.exceptions
import tuf.log
import tuf.formats
import tuf.keydb
import tuf.roledb
import tuf.repository_tool as repo_tool
import tuf.repository_lib as repo_lib
import tuf.unittest_toolbox as unittest_toolbox
import tuf.client.updater as tuf_updater
import securesystemslib
import six
import json
from pathlib import Path
from taf.updater.handlers import GitUpdater
from taf.updater.exceptions import UpdateFailed


def update(url, clients_directory, repo_name):
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
        repository_updater._get_target_file(target_filepath, trusted_length,
          trusted_hashes)
        print(f'Successfully validated file {target_filepath} at {repository_updater.update_handler.current_commit}')

  except Exception as e:
    # for now, useful for debugging
    traceback.print_exc()
    raise UpdateFailed(f'Failed to update authentication repository {clients_directory} due to error: {e}')
  finally:
    repository_updater.update_handler.cleanup()

  # successfully validated the authentication repository, it is safe to pull the changes
  # up until the latest validated commit
  # fetch and merge up until a commit
  users_auth_repo = repository_updater.update_handler.users_auth_repo
  last_commit = repository_updater.update_handler.commits[-1]
  users_auth_repo.clone_or_pull_up_to_commit(last_commit)
