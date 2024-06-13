import json
from pathlib import Path
import re
import shutil
from functools import partial
from taf.api.repository import create_repository
from taf.api.targets import register_target_files, update_target_repos_from_repositories_json
from taf.git import GitRepository
from taf.repositoriesdb import (
    DEPENDENCIES_JSON_NAME,
    MIRRORS_JSON_NAME,
    REPOSITORIES_JSON_NAME,
)
from taf.tests.conftest import (
    TEST_DATA_ORIGIN_PATH,
    KEYSTORE_PATH,
    TEST_INIT_DATA_PATH,
    origin_repos_group,
)
from taf.utils import on_rm_error
from tuf.ngclient._internal import trusted_metadata_set
from pytest import fixture
from tuf.repository_tool import TARGETS_DIRECTORY_NAME
from jinja2 import Environment, BaseLoader

original_tuf_trusted_metadata_set = trusted_metadata_set.TrustedMetadataSet

NAMESPACE1 = "namespace1"
NAMESPACE2 = "namespace2"
TARGET1_NAME = "target1"
TARGET2_NAME = "target2"
TARGET3_NAME = "target3"
AUTH_NAME = "auth"
ROOT_REPO_NAMESPACE = "root"


# test_config.py

class RepositoryConfig:
    def __init__(self, name, allow_unauthenticated_commits=False):
        self.name = name
        self.allow_unauthenticated_commits = allow_unauthenticated_commits

class TestConfig:

    def __init__(self, library_dir, auth_repo_config: RepositoryConfig, target_repo_configs: RepositoryConfig):
        self.library_dir = library_dir
        self.auth_repo_config = auth_repo_config
        self.target_repo_configs = target_repo_configs


def initialize_git_repo(library_dir: Path, repo_name: str):
    repo_path = Path(library_dir, repo_name)
    repo_path.mkdir(parents=True, exist_ok=True)
    repo = GitRepository(repo_path=repo_path)
    repo.init_repo()

def create_repositories_json(library_dir, repo_name, targets_config: list[RepositoryConfig]):
    repo_path = Path(library_dir, repo_name)
    targets_dir_path = repo_path / TARGETS_DIRECTORY_NAME
    targets_dir_path.mkdir(parents=True, exist_ok=True)
    if len(targets_config):
        repositories_json = create_repositories_json(targets_config)
        (targets_dir_path / REPOSITORIES_JSON_NAME).write_text(repositories_json)

def create_mirrors_json(library_dir, repo_name):
    repo_path = Path(library_dir, repo_name)
    targets_dir_path = repo_path / TARGETS_DIRECTORY_NAME
    targets_dir_path.mkdir(parents=True, exist_ok=True)
    mirrors = {"mirrors": [f"{library_dir}/{{org_name}}/{{repo_name}}"]}
    mirrors_path = repo_path / MIRRORS_JSON_NAME
    mirrors_path.write_text(json.dumps(mirrors))


def create_authentication_repository(library_dir, repo_name, keys_description):
    repo_path = Path(library_dir, repo_name)
    create_repository(
        str(repo_path), str(KEYSTORE_PATH), keys_description, commit=True
    )

def sign_target_files(library_dir, repo_name, keystore):
    repo_path = Path(library_dir, repo_name)
    register_target_files(str(repo_path), keystore)

def initialize_target_repositories(library_dir, targets_config: list[RepositoryConfig]):
    for target_config in targets_config:
        target_repo = initialize_git_repo(library_dir=library_dir, repo_name=target_config.name)
        # create some files, content of these repositories is not important
        for i in range(1, 3):
            (target_repo.path / f"test{i}.txt").write_text(f"Test file {i}")
        target_repo.commit("Initial commit")
        return target_repo

def sign_target_repositories(library_dir, repo_name, keystore):
    repo_path = Path(library_dir, repo_name)
    update_target_repos_from_repositories_json(
        str(repo_path),
        str(library_dir),
        str(keystore),
    )

def update_target_repositories(library_dir, repo_name, targets_config: list[RepositoryConfig]):
    for target_config in targets_config:
        target_repo = GitRepository(library_dir, target_config.name)
        update_target_files(target_repo, "Update target files")

class TaskManager:
    def __init__(self, library_dir, repo_name):
        self.library_dir = library_dir
        self.repo_name = repo_name
        self.tasks = []

    def add_task(self, func, **kwargs):
        # Create a task with repo_path set, and only variable parameters need passing later
        task = partial(func, library_dir=self.library_dir, repo_name=self.repo_name **kwargs)
        self.tasks.append(task)

    def run_tasks(self):
        for task in self.tasks:
            task()


def valid_repository_setup_no_unauthenticated_commits(repo_name, keys_description, targets_config):
    setup_manager = TaskManager(TEST_DATA_ORIGIN_PATH, repo_name)
    setup_manager.add_task(initialize_git_repo)
    setup_manager.add_task(create_repositories_json, targets_config=targets_config)
    setup_manager.add_task(create_mirrors_json)
    setup_manager.add_task(create_authentication_repository, keys_description)
    setup_manager.add_task(initialize_target_repositories, targets_config=targets_config)
    setup_manager.add_task(sign_target_repositories, keystore=KEYSTORE_PATH)
    setup_manager.add_task(update_target_repositories, targets_config=targets_config)
    setup_manager.add_task(sign_target_repositories, keystore=KEYSTORE_PATH)
    setup_manager.add_task(update_target_repositories, targets_config=targets_config)
    setup_manager.add_task(sign_target_repositories, keystore=KEYSTORE_PATH)
    setup_manager.run_tasks()



@fixture(scope="session", autouse=True)
def updater_repositories():
    test_dir = "test-updater"
    with origin_repos_group(test_dir) as origins:
        yield origins


def initialize_repo(namespace, repo_name):
    repo_path = TEST_DATA_ORIGIN_PATH / namespace / repo_name
    repo_path.mkdir(parents=True, exist_ok=True)
    repo = GitRepository(path=repo_path)
    repo.init_repo()
    return repo




def initialize_target_repo(namespace, repo_name):
    repo = initialize_repo(namespace, repo_name)
    # create some files
    for i in range(1, 3):
        (repo.path / f"test{i}.txt").write_text(f"Test file {i}")
    repo.commit("Initial commit")
    return repo


def update_target_files(target_repo, commit_message):
    text_to_add = "Some text to add"
    # Iterate over all files in the repository directory
    for file_path in target_repo.path.iterdir():
        if file_path.is_file():
            existing_content = file_path.read_text(encoding="utf-8")
            new_content = existing_content + "\n" + text_to_add
            file_path.write_text(new_content, encoding="utf-8")
    target_repo.commit(commit_message)


def create_repositories_json(targets_data: list[RepositoryConfig]):
    template_str = (TEST_INIT_DATA_PATH / "repositories.j2").read_text()
    env = Environment(loader=BaseLoader())
    template = env.from_string(template_str)
    return template.render(targets_data=targets_data)

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
