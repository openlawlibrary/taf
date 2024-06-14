from collections import defaultdict
import json
from pathlib import Path
from functools import partial
from jinja2 import Environment, BaseLoader
from taf.updater.types.update import UpdateType
from tuf.repository_tool import TARGETS_DIRECTORY_NAME
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
)


KEYS_DESCRIPTION = str(TEST_INIT_DATA_PATH / "keys.json")

class RepositoryConfig:
    def __init__(self, name, allow_unauthenticated_commits=False):
        self.name = name
        self.allow_unauthenticated_commits = allow_unauthenticated_commits

class Task:

    def __init__(self, library_dir, repo_name, functions, func_params=None):
        if func_params is None:
            func_params = []
        if not isinstance(functions, list):
            functions_list = [functions]
        else:
            functions_list = functions

        self.functions = []
        for index, function in enumerate(functions_list):
            kwargs = {}
            if index < len(func_params):
                kwargs = func_params[index]
            self.functions.append(partial(function, library_dir=library_dir, repo_name=repo_name, **kwargs))

    def run(self):
        for function in self.functions:
            function()


class TaskManager:
    def __init__(self, library_dir, repo_name):
        self.library_dir = library_dir
        self.repo_name = repo_name
        self.tasks = []

    def add_task(self, functions, func_params=None):
        task = Task(self.library_dir, self.repo_name, functions, func_params)
        self.tasks.append(task)

    def run_tasks(self):
        for task in self.tasks:
            task.run()


def initialize_git_repo(library_dir: Path, repo_name: str):
    repo_path = Path(library_dir, repo_name)
    repo_path.mkdir(parents=True, exist_ok=True)
    repo = GitRepository(path=repo_path)
    repo.init_repo()
    return repo

def create_repositories_json(library_dir, repo_name, targets_config: list[RepositoryConfig]):
    repo_path = Path(library_dir, repo_name)
    targets_dir_path = repo_path / TARGETS_DIRECTORY_NAME
    targets_dir_path.mkdir(parents=True, exist_ok=True)
    if len(targets_config):
        repositories_json = generate_repositories_json(targets_config)
        (targets_dir_path / REPOSITORIES_JSON_NAME).write_text(repositories_json)


def create_info_json(library_dir, repo_name):
    repo_path = Path(library_dir, repo_name)
    targets_dir_path = repo_path / TARGETS_DIRECTORY_NAME
    protected_dir = targets_dir_path / "protected"
    protected_dir.mkdir(parents=True, exist_ok=True)
    info_json_path = protected_dir / "info.json"
    info_content = {"namespace": repo_name.split("/")[0], "name": repo_name.split("/")[1]}
    info_json_path.write_text(json.dumps(info_content))


def create_mirrors_json(library_dir, repo_name):
    repo_path = Path(library_dir, repo_name)
    targets_dir_path = repo_path / TARGETS_DIRECTORY_NAME
    targets_dir_path.mkdir(parents=True, exist_ok=True)
    mirrors = {"mirrors": [f"{library_dir}/{{org_name}}/{{repo_name}}"]}
    mirrors_path = targets_dir_path / MIRRORS_JSON_NAME
    mirrors_path.write_text(json.dumps(mirrors))


def create_authentication_repository(library_dir, repo_name, keys_description):
    repo_path = Path(library_dir, repo_name)
    create_repository(
        str(repo_path), str(KEYSTORE_PATH), keys_description, commit=True
    )


def sign_target_files(library_dir, repo_name, keystore):
    repo_path = Path(library_dir, repo_name)
    register_target_files(str(repo_path), keystore, write=True)


def initialize_target_repositories(library_dir, repo_name, targets_config: list):
    for target_config in targets_config:
        target_repo = initialize_git_repo(library_dir=library_dir, repo_name=target_config.name)
        # create some files, content of these repositories is not important
        for i in range(1, 3):
            (target_repo.path / f"test{i}.txt").write_text(f"Test file {i}")
        target_repo.commit("Initial commit")


def sign_target_repositories(library_dir, repo_name, keystore):
    repo_path = Path(library_dir, repo_name)
    update_target_repos_from_repositories_json(
        str(repo_path),
        str(library_dir),
        str(keystore),
    )


def generate_repositories_json(targets_data: list[RepositoryConfig]):
    template_str = (TEST_INIT_DATA_PATH / "repositories.j2").read_text()
    env = Environment(loader=BaseLoader())
    template = env.from_string(template_str)
    return template.render(targets_data=targets_data)
