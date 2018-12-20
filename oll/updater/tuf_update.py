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

import tuf
import tuf.exceptions
import tuf.log
import tuf.formats
import tuf.keydb
import tuf.roledb
import tuf.repository_tool as repo_tool
import tuf.repository_lib as repo_lib
import tuf.unittest_toolbox as unittest_toolbox
import tuf.client.updater as updater

import securesystemslib
import six
import json
from pathlib import Path
from handlers import GitMetadataUpdater


def update():
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

    # temporary, during initial development
    clients_directory = 'E:\\OLL\\tuf_updater_test'
    repository_name = 'dc-law'

    clients_reposiotry = os.path.join(clients_directory, repository_name)
    clients_keystore = os.path.join(clients_directory, 'keystore')
    clients_metadata = os.path.join(clients_reposiotry, 'metadata')

    # Setting 'tuf.settings.repository_directory' with the temporary client
    # directory copied from the original repository files.
    tuf.settings.repositories_directory = clients_directory

    url_prefix = 'https://github.com/openlawlibrary/dc-law'
    repository_mirrors = {'mirror1': {'url_prefix': url_prefix,
                                      'metadata_path': 'metadata',
                                      'targets_path': '',
                                      'confined_target_dirs': ['']}}

    # Creating a repository instance.  The test cases will use this client
    # updater to refresh metadata, fetch target files, etc.
    repository_updater = updater.Updater(repository_name,
                                         repository_mirrors,
                                         GitMetadataUpdater)

    update_done = False
    try:
        while not update_done:
            repository_updater.refresh()
            repository_updater._refresh_targets_metadata()
            update_done = repository_updater.update_handler.update_done()
    except Exception as e:
        print(e)
    repository_updater.update_handler.cleanup()

update()
