from datetime import datetime
import json
import pytest
import re
import shutil
from freezegun import freeze_time
from pathlib import Path
from functools import partial
from taf.api.repository import create_repository
from taf.api.targets import (
    register_target_files,
    update_target_repos_from_repositories_json,
)
from taf.git import GitRepository
from taf.repositoriesdb import (
    DEPENDENCIES_JSON_NAME,
    MIRRORS_JSON_NAME,
    REPOSITORIES_JSON_NAME,
)
from taf.api.metadata import (
    _update_expiration_date_of_role,
    update_metadata_expiration_date,
)
from taf.auth_repo import AuthenticationRepository
from taf.constants import DEFAULT_RSA_SIGNATURE_SCHEME
from taf.messages import git_commit_message
from taf.tests.test_updater.conftest import (
    KEYS_DESCRIPTION,
    RepositoryConfig,
    TaskManager,
    create_authentication_repository,
    create_info_json,
    create_mirrors_json,
    create_repositories_json,
    initialize_target_repositories,
    sign_target_repositories,
)
from taf.tests.conftest import (
    CLIENT_DIR_PATH,
    TEST_DATA_ORIGIN_PATH,
    KEYSTORE_PATH,
    TEST_INIT_DATA_PATH,
    origin_repos_group,
)
from taf.api.utils._git import commit_and_push
from taf.utils import on_rm_error
from tuf.ngclient._internal import trusted_metadata_set
from pytest import fixture
from tuf.repository_tool import TARGETS_DIRECTORY_NAME


original_tuf_trusted_metadata_set = trusted_metadata_set.TrustedMetadataSet

NAMESPACE1 = "namespace1"
NAMESPACE2 = "namespace2"
TARGET1_NAME = "target1"
TARGET2_NAME = "target2"
TARGET3_NAME = "target3"
AUTH_NAME = "auth"
ROOT_REPO_NAMESPACE = "root"


# test_config.py


def initialize_repo(namespace, repo_name):
    repo_path = TEST_DATA_ORIGIN_PATH / namespace / repo_name
    repo_path.mkdir(parents=True, exist_ok=True)
    repo = GitRepository(path=repo_path)
    repo.init_repo()
    return repo


def initialize_target_repo(namespace, repo_name):
    repo_path = TEST_DATA_ORIGIN_PATH / namespace / repo_name

    if not repo_path.is_dir():
        repo = initialize_repo(namespace, repo_name)
    else:
        repo = GitRepository(path=repo_path)

    # create some files
    # it is not important what these repositories contain
    for i in range(1, 3):
        (repo.path / f"test{i}.txt").write_text(f"Test file {i}")
    repo.commit("Initial commit")
    return repo


def create_and_write_json(template_path, substitutions, output_path):
    template = template_path.read_text()
    for key, value in substitutions.items():
        template = re.sub(rf"\{{{key}\}}", value, template)
    output_path.write_text(template)


def create_mirrors(auth_repo):
    mirrors = {"mirrors": [f"{TEST_DATA_ORIGIN_PATH}/{{org_name}}/{{repo_name}}"]}
    mirrors_path = auth_repo.path / TARGETS_DIRECTORY_NAME / MIRRORS_JSON_NAME
    mirrors_path.write_text(json.dumps(mirrors))


def create_auth_repo_with_repositories_json_and_mirrors(
    namespace, json_template_path, json_output_dir
):
    auth_repo = initialize_repo(namespace, AUTH_NAME)
    (auth_repo.path / TARGETS_DIRECTORY_NAME).mkdir(parents=True, exist_ok=True)
    create_and_write_json(
        json_template_path,
        {"namespace": namespace},
        json_output_dir
        / auth_repo.path
        / TARGETS_DIRECTORY_NAME
        / REPOSITORIES_JSON_NAME,
    )
    create_mirrors(auth_repo)
    keys_description = str(TEST_INIT_DATA_PATH / "keys.json")
    create_repository(
        str(auth_repo.path), str(KEYSTORE_PATH), keys_description, commit=True
    )
    return auth_repo


def create_target_repos(namespace, target_names, auth_repo_path, num_updates=2):
    target_repos = [initialize_target_repo(namespace, name) for name in target_names]
    update_target_repos_from_repositories_json(
        str(auth_repo_path),
        str(TEST_DATA_ORIGIN_PATH),
        str(KEYSTORE_PATH),
    )
    for _ in range(num_updates):
        for target_repo in target_repos:
            update_target_files(target_repo, "Update target files")
        update_target_repos_from_repositories_json(
            str(auth_repo_path),
            str(TEST_DATA_ORIGIN_PATH),
            str(KEYSTORE_PATH),
        )
    return target_repos


@fixture
def library_with_dependencies():
    library = {}

    namespaces = [NAMESPACE1, NAMESPACE2]
    target_names = [TARGET1_NAME, TARGET2_NAME, TARGET3_NAME]

    initial_commits = []
    for namespace in namespaces:
        auth_repo = create_auth_repo_with_repositories_json_and_mirrors(
            namespace,
            TEST_INIT_DATA_PATH / REPOSITORIES_JSON_NAME,
            TEST_DATA_ORIGIN_PATH,
        )
        initial_commits.append(auth_repo.head_commit_sha())
        target_repos = create_target_repos(namespace, target_names, auth_repo.path)
        library[auth_repo.name] = {"auth_repo": auth_repo, "target_repos": target_repos}

    root_auth_repo = initialize_repo(ROOT_REPO_NAMESPACE, AUTH_NAME)
    (root_auth_repo.path / TARGETS_DIRECTORY_NAME).mkdir(parents=True, exist_ok=True)
    create_and_write_json(
        TEST_INIT_DATA_PATH / DEPENDENCIES_JSON_NAME,
        {"commit1": initial_commits[0], "commit2": initial_commits[1]},
        root_auth_repo.path / TARGETS_DIRECTORY_NAME / DEPENDENCIES_JSON_NAME,
    )
    create_mirrors(root_auth_repo)
    keys_description = str(TEST_INIT_DATA_PATH / "keys.json")
    create_repository(
        str(root_auth_repo.path), str(KEYSTORE_PATH), keys_description, commit=True
    )
    library[root_auth_repo.name] = {"auth_repo": root_auth_repo, "target_repos": []}

    yield library

    for repo_info in library.values():
        auth_repo = repo_info["auth_repo"]
        target_repos = repo_info["target_repos"]

        shutil.rmtree(auth_repo.path, onerror=on_rm_error)

        for target_repo in target_repos:
            shutil.rmtree(target_repo.path, onerror=on_rm_error)
