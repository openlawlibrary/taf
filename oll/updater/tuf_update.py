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
    # Copy the original repository files provided in the test folder so that
    # any modifications made to repository files are restricted to the copies.
    # The 'repository_data' directory is expected to exist in 'tuf.tests/'.
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
    while not update_done:
        repository_updater.refresh()
        repository_updater._refresh_targets_metadata()
        update_done = repository_updater.update_handler.update_done()

update()
