import enum
import os
import re
import uuid

from taf.models.types import Commitish
import pytest
import inspect
import random
import shutil
import string
import json
from typing import Optional
from functools import partial
from freezegun import freeze_time
from pathlib import Path
from jinja2 import Environment, BaseLoader
from taf.api.api_workflow import manage_repo_and_signers
from taf.api.metadata import (
    update_metadata_expiration_date,
)
from taf.auth_repo import AuthenticationRepository
from taf.constants import DEFAULT_RSA_SIGNATURE_SCHEME, TARGETS_DIRECTORY_NAME
from taf import repositoriesdb, settings
from taf.exceptions import GitError
from taf.utils import on_rm_error
from taf.log import disable_console_logging
from taf.tests.test_updater.update_utils import load_target_repositories
from taf.api.repository import create_repository
from taf.api.targets import (
    register_target_files,
    update_target_repos_from_repositories_json,
)
from taf.git import GitRepository
from taf.repositoriesdb import (
    MIRRORS_JSON_NAME,
    REPOSITORIES_JSON_NAME,
)
from taf.tests.conftest import (
    CLIENT_DIR_PATH,
    TEST_DATA_ORIGIN_PATH,
    KEYSTORE_PATH,
    TEST_INIT_DATA_PATH,
)
from taf.yubikey.yubikey_manager import PinManager

from tuf.api.metadata import Timestamp


KEYS_DESCRIPTION = str(TEST_INIT_DATA_PATH / "keys.json")


TARGET_MISSMATCH_PATTERN = r"Update of (\w+)\/(\w+) failed due to error: Failure to validate (\w+)\/(\w+) commit ([0-9a-f]{40}) committed on (\d{4}-\d{2}-\d{2}): data repository ([\w\/-]+) was supposed to be at commit ([0-9a-z]{40}) but repo was at ([0-9a-f]{40})"
TARGET_MISMATCH_PATTERN_DEPENDENCIES = r"Update of (\w+)/(\w+) failed due to error: Update of (\w+)/(\w+) failed. One or more referenced authentication repositories could not be validated:\n Failure to validate (\w+)/(\w+) commit ([0-9a-f]{40}) committed on (\d{4}-\d{2}-\d{2}): data repository ([\w\/-]+) was supposed to be at commit ([0-9a-f]{40}) but repo was at ([0-9a-f]{40})"
TARGET_ADDITIONAL_COMMIT_PATTERN = r"Update of (\w+)\/(\w+) failed due to error: Failure to validate (\w+)\/(\w+) commit ([0-9a-f]{40}) committed on (\d{4}-\d{2}-\d{2}): data repository ([\w\/-]+) was supposed to be at commit ([0-9a-f]{40}) but commit not on branch (\w+)"
TARGET_COMMIT_AFTER_LAST_VALIDATED_PATTERN = r"Update of (\w+)\/(\w+) failed due to error: Target repository ([\w\/-]+) does not allow unauthenticated commits, but contains commit\(s\) ([0-9a-f]{40}(?:, [0-9a-f]{40})*) on branch (\w+)"
TARGET_MISSING_COMMIT_PATTERN = r"Update of (\w+)/(\w+) failed due to error: Failure to validate (\w+)/(\w+) commit ([0-9a-f]{40}) committed on (\d{4}-\d{2}-\d{2}): data repository ([\w\/-]+) was supposed to be at commit ([0-9a-f]{40}) but commit not on branch (\w+)"
NOT_CLEAN_PATTERN = r"^Update of ([\w/]+) failed due to error: Repository ([\w/-]+) should contain only committed changes\."
INVALID_KEYS_PATTERN = r"^Update of (\w+)\/(\w+) failed due to error: Validation of authentication repository (\w+)/(\w+) failed at revision ([0-9a-f]{40}) due to error: ([\w/-]+) was signed by (\d+)/(\d+) keys$"
INVALID_METADATA_PATTERN = r"^Update of (\w+)\/(\w+) failed due to error: Validation of authentication repository (\w+)/(\w+) failed at revision ([0-9a-f]{40}) due to error: Invalid metadata file ([\w/]+\.\w+)$"
INVALID_VERSION_NUMBER_PATTERN = r"^Update of (\w+\/\w+) failed due to error: Validation of authentication repository (\w+\/\w+) failed at revision ([0-9a-f]+) due to error: New (\w+) version (\d) must be >= (\d+)$"
WRONG_UPDATE_TYPE_TEST_REPO = r"Update of (\w+\/\w+) failed due to error: Repository (\w+\/\w+) is a test repository. Call update with \"--expected-repo-type\" test to update a test repository$"
WRONG_UPDATE_TYPE_OFFICIAL_REPO = r"Update of (\w+\/\w+) failed due to error: Repository (\w+\/\w+) is not a test repository, but update was called with the \"--expected-repo-type\" test$"
METADATA_EXPIRED = r"Update of (\w+\/\w+) failed due to error: Validation of authentication repository (\w+\/\w+) failed at revision [0-9a-f]+ due to error: .+ is expired"
NO_INFO_JSON = "Update of repository failed due to error: Error during info.json parse. If the authentication repository's path is not specified, info.json metadata is expected to be in targets/protected"
UNCOMMITTED_CHANGES = r"Update of (\w+\/\w+) failed due to error: Repository (\w+\/\w+) should contain only committed changes\. \nPlease update the repository at (.+) manually and try again\."
UPDATE_ERROR_PATTERN = r"Update of (\w+\/\w+) failed due to error: Validation of authentication repository (\w+\/\w+) failed at revision ([0-9a-f]+) due to error: .*"
FORCED_UPDATE_PATTERN = r"Update of (\w+\/\w+) failed due to error: Repositories ([\w/,\s-]+) have uncommitted changes. Commit and push or use --force to revert and run the command again."
BEHIND_LVC_PATTERN = r"Update of (\w+\/\w+) failed due to error: Top commit of repository \1 ([0-9a-f]{40}) is not equal to or newer than the last successful commit."
LVC_NOT_IN_REPO_PATTERN = r"Update of (\w+\/\w+) failed due to error: \1: Last validated commit (\w{40}) is not in repository \1\s*Run the updater with the --force flag to run the validation from the first commit"
LVC_NOT_IN_REMOTE_PATTERN = r"Update of ([\w_\/]+) failed due to error: Last validated commit ([\da-f]{40}) is no longer on (\w+) of the remote ([\w_\/]+) repository.*"
UNPUSHED_COMMITS_PATTERN = r"Update of (\w+\/\w+) failed due to error:\s*\nThe following repository has unpushed commits on branches: ([\w\/]+): \(([\w,-]+)\)"
REMOVED_COMMITS_PATTERN = r"Update of (\w+/\w+) failed due to error: Last validated commit ([0-9a-f]{40}) is not in the remote repository."
INVALID_TIMESTAMP_PATTERN = r"^Update of (\w+\/\w+) failed due to error: Update of (\w+\/\w+) failed. One or more referenced authentication repositories could not be validated:\n Validation of authentication repository (\w+\/\w+) failed at revision ([0-9a-f]{40}) due to error: timestamp was signed by (\d+)\/(\d+) keys$"
CANNOT_CLONE_TARGET_PATTERN = r"^Update of (\w+/\w+) failed due to error: Update of (\w+/\w+) failed. One or more referenced authentication repositories could not be validated:\n Cannot clone (\w+/\w+) from any of the following URLs: \['.*'\]$"
INVALID_TIMESTAMP_PATTERN_ROOT = r"^Update of (\w+\/\w+) failed due to error: Validation of authentication repository (\w+\/\w+) failed at revision ([0-9a-f]{40}) due to error: timestamp was signed by (\d+)\/(\d+) keys$"
TARGET_COMMIT_NOT_ON_BRANCH_PATTERN = r"Update of (\w+\/\w+) failed due to error: Failure to validate (\w+\/\w+) commit ([0-9a-f]{40}) committed on (\d{4}-\d{2}-\d{2}): data repository (\w+\/\w+) was supposed to be at commit ([0-9a-f]{40}) but commit not on branch (\w+)"
TARGET_COMMIT_MISMATCH_PATTERN = (
    r"Update of (\w+\/\w+) failed due to error: Failure to validate (\w+\/\w+) commit "
    r"([0-9a-f]{40}) committed on (\d{4}-\d{2}-\d{2}): data repository (\w+\/\w+) was "
    r"supposed to be at commit ([0-9a-f]{40}) but (repo was at|commit not on branch) (\w+)"
)


# Disable console logging for all tests
disable_console_logging()


# Update the settings before each test module runs
@pytest.fixture(scope="module", autouse=True)
def update_settings_before_module():
    settings.update_from_filesystem = True
    yield
    settings.update_from_filesystem = False


@pytest.fixture(autouse=True)
def run_around_tests(client_dir, origin_dir):
    yield
    cleanup_directory(client_dir)
    cleanup_directory(origin_dir)


class SetupState(enum.Enum):
    # All files needed by the framework added during initialization of the
    # authentication repository
    # Currently, those are:
    #   - protected/info.json
    #   - mirrors.json
    #   - repositories.json
    # Target repositories are created and their commits are signed
    ALL_FILES_INITIALLY = "all_files_initially"
    # Create an authentication repository without protected/info.json
    NO_INFO_JSON = "no_info_json"
    # mirrors.json is not added while initializing the repository
    # it is added in another commmit later
    MIRRORS_ADDED_LATER = "mirrors_added_later"
    # both mirrors.json and repositories.json are added after the
    # repository's initialization
    MIRRORS_AND_REPOSITOIRES_ADDED_LATER = "repositories_and_mirrors_added_later"
    # Create just the authentication repository, without target repositories
    NO_TARGET_REPOSITORIES = "no_target_repositories"


class Task:
    """
    Task that is run by the SetupManager.
    When the task is executed, the specified function will
    be invoked with the listed parameters, if any.
    Date can be used to modify the current time, allowing
    us to set up states where metadata has expired, etc.
    Repetitions can be set to determine if the function should be called multiple
    times in sequential order.
    """

    def __init__(self, function, date, repetitions, params):
        self.function = function
        self.params = params
        self.date = date
        self.repetitions = repetitions


class SetupManager:
    """
    Class which is meant to make it easier to run setup functions
    by abstracting away details like how target repositories are
    loaded and how to simulate execution of function at any date and time
    """

    def __init__(self, auth_repo):
        self.auth_repo = auth_repo
        self.target_repos = load_target_repositories(auth_repo).values()
        self.tasks = []

    def add_task(self, function, kwargs=None):
        if kwargs is None:
            kwargs = {}
        date = kwargs.pop("date", None)
        repetitions = kwargs.pop("repetitions", 1)
        sig = inspect.signature(function)
        if "pin_manager" in sig.parameters:
            function = partial(function, pin_manager=self.auth_repo.pin_manager)
        if "auth_repo" in sig.parameters:
            function = partial(function, auth_repo=self.auth_repo)
        # Check if the parameter is in the signature
        if "target_repos" in sig.parameters:
            function = partial(function, target_repos=self.target_repos)
        self.tasks.append(Task(function, date, repetitions, kwargs))

    def execute_tasks(self):
        for task in self.tasks:
            for _ in range(task.repetitions):
                if task.date is not None:
                    with freeze_time(task.date):
                        task.function(**task.params)
                else:
                    task.function(**task.params)
        # remove all tasks once they are all executed
        # allow for the reuse of the setup manager
        self.tasks = []
        repositoriesdb.clear_repositories_db()


class RepositoryConfig:
    def __init__(
        self,
        name: str,
        allow_unauthenticated_commits: bool = False,
        is_empty: bool = False,
    ):
        self.name = name
        self.allow_unauthenticated_commits = allow_unauthenticated_commits
        self.is_empty = is_empty


@pytest.fixture
def client_dir():
    yield CLIENT_DIR_PATH


@pytest.fixture
def origin_dir():
    yield TEST_DATA_ORIGIN_PATH


@pytest.fixture(scope="function")
def test_name(request):
    # Extract the test name and the counter
    match = re.match(r"(.+?)\[-?\w+(\d+)\]?", request.node.name)
    if match:
        test_name, counter = match.groups()
        return f"{test_name}{counter}"
    else:
        return request.node.name


@pytest.fixture(scope="function")
def origin_auth_repo(
    request, test_name: str, origin_dir: Path, pin_manager: PinManager
):
    targets_config_list = request.param["targets_config"]
    is_test_repo = request.param.get("is_test_repo", False)
    date = request.param.get("data")
    setup_type = request.param.get("setup_type", SetupState.ALL_FILES_INITIALLY)
    targets_config = [
        RepositoryConfig(
            f"{test_name}/{targets_config['name']}",
            targets_config.get("allow_unauthenticated_commits", False),
            targets_config.get("is_empty", False),
        )
        for targets_config in targets_config_list
    ]
    repo_name = f"{test_name}/auth"

    if date is not None:
        with freeze_time(date):
            auth_repo = _init_auth_repo(
                origin_dir,
                setup_type,
                repo_name,
                targets_config,
                is_test_repo,
                pin_manager,
            )
    else:
        auth_repo = _init_auth_repo(
            origin_dir, setup_type, repo_name, targets_config, is_test_repo, pin_manager
        )

    yield auth_repo


def cleanup_directory(directory_path: Path):
    """Recursively clean up the directory, removing files and directories."""
    try:
        if directory_path.is_dir():
            shutil.rmtree(directory_path, onerror=on_rm_error)
    except Exception:
        pass


def clone_client_repo(target_name: str, origin_dir: Path, client_dir: Path):
    origin_repo_path = origin_dir / target_name
    client_repo = GitRepository(client_dir, target_name)
    client_repo.clone_from_disk(origin_repo_path, keep_remote=True)
    return client_repo


def create_repositories_json(library_dir: Path, repo_name: str, targets_config: list):
    repo_path = Path(library_dir, repo_name)
    targets_dir_path = repo_path / TARGETS_DIRECTORY_NAME

    try:
        targets_dir_path.mkdir(parents=True, exist_ok=True)
    except PermissionError:
        # Attempt to fix permissions
        os.chmod(repo_path, 0o775)
        targets_dir_path.mkdir(parents=True, exist_ok=True)

    if len(targets_config):
        repositories_json = generate_repositories_json(targets_config)
        (targets_dir_path / REPOSITORIES_JSON_NAME).write_text(repositories_json)


def create_info_json(library_dir: Path, repo_name: str):
    repo_path = Path(library_dir, repo_name)
    targets_dir_path = repo_path / TARGETS_DIRECTORY_NAME
    protected_dir = targets_dir_path / "protected"
    protected_dir.mkdir(parents=True, exist_ok=True)
    info_json_path = protected_dir / "info.json"
    info_content = {
        "namespace": repo_name.split("/")[0],
        "name": repo_name.split("/")[1],
    }
    info_json_path.write_text(json.dumps(info_content))


def create_mirrors_json(library_dir: Path, repo_name: str):
    repo_path = Path(library_dir, repo_name)
    targets_dir_path = repo_path / TARGETS_DIRECTORY_NAME
    targets_dir_path.mkdir(parents=True, exist_ok=True)
    mirrors = {"mirrors": [f"{library_dir}/{{org_name}}/{{repo_name}}"]}
    mirrors_path = targets_dir_path / MIRRORS_JSON_NAME
    mirrors_path.write_text(json.dumps(mirrors))


def create_authentication_repository(
    library_dir: Path,
    pin_manager: PinManager,
    repo_name: str,
    keys_description: str,
    is_test_repo: bool = False,
):
    repo_path = Path(library_dir, repo_name)
    create_repository(
        str(repo_path),
        pin_manager,
        str(KEYSTORE_PATH),
        keys_description,
        commit=True,
        test=is_test_repo,
    )


def sign_target_files(library_dir, repo_name, keystore, pin_manager):
    repo_path = Path(library_dir, repo_name)
    register_target_files(str(repo_path), pin_manager, keystore)


def _init_auth_repo(
    origin_dir: Path,
    setup_type: str,
    repo_name: str,
    targets_config: list,
    is_test_repo: bool,
    pin_manager: PinManager,
) -> AuthenticationRepository:
    if setup_type == SetupState.ALL_FILES_INITIALLY:
        return setup_repository_all_files_initially(
            origin_dir, repo_name, targets_config, is_test_repo, pin_manager
        )
    elif setup_type == SetupState.NO_INFO_JSON:
        return setup_repository_no_info_json(
            origin_dir, repo_name, targets_config, is_test_repo, pin_manager
        )
    elif setup_type == SetupState.MIRRORS_ADDED_LATER:
        return setup_repository_mirrors_added_later(
            origin_dir, repo_name, targets_config, is_test_repo, pin_manager
        )
    elif setup_type == SetupState.MIRRORS_AND_REPOSITOIRES_ADDED_LATER:
        return setup_repository_repositories_and_mirrors_added_later(
            origin_dir, repo_name, targets_config, is_test_repo, pin_manager
        )
    elif setup_type == SetupState.NO_TARGET_REPOSITORIES:
        return setup_repository_no_target_repositories(
            origin_dir, repo_name, targets_config, is_test_repo, pin_manager
        )
    else:
        raise ValueError(f"Unsupported setup type: {setup_type}")


def initialize_git_repo(library_dir: Path, repo_name: str) -> GitRepository:
    repo_path = Path(library_dir, repo_name)
    if repo_path.is_dir():
        shutil.rmtree(repo_path, onerror=on_rm_error)
    repo_path.mkdir(parents=True, exist_ok=True)
    repo = GitRepository(path=repo_path)
    repo.init_repo()
    return repo


def initialize_target_repositories(
    library_dir: Path, targets_config: list, create_new_repo=True
):
    for target_config in targets_config:
        if create_new_repo:
            target_repo = initialize_git_repo(
                library_dir=library_dir, repo_name=target_config.name
            )
        else:
            target_repo = GitRepository(library_dir, target_config.name)
        # create some files, content of these repositories is not important
        if not target_config.is_empty:
            for i in range(1, 3):
                random_text = _generate_random_text()
                (target_repo.path / f"test{i}.txt").write_text(random_text)
            target_repo.commit("Initial commit")


def sign_target_repositories(
    library_dir: Path, repo_name: str, keystore: Path, pin_manager: PinManager
):
    repo_path = Path(library_dir, repo_name)
    update_target_repos_from_repositories_json(
        str(repo_path),
        pin_manager,
        str(library_dir),
        str(keystore),
    )


def generate_repositories_json(targets_data: list):
    template_str = (TEST_INIT_DATA_PATH / "repositories.j2").read_text()
    env = Environment(loader=BaseLoader())
    template = env.from_string(template_str)
    return template.render(targets_data=targets_data)


def setup_repository_all_files_initially(
    origin_dir: Path,
    repo_name: str,
    targets_config: list,
    is_test_repo: bool,
    pin_manager: PinManager,
) -> AuthenticationRepository:
    # Define the origin path
    # Execute the tasks directly
    create_repositories_json(origin_dir, repo_name, targets_config=targets_config)
    create_mirrors_json(origin_dir, repo_name)
    create_info_json(origin_dir, repo_name)
    create_authentication_repository(
        origin_dir,
        pin_manager,
        repo_name,
        keys_description=KEYS_DESCRIPTION,
        is_test_repo=is_test_repo,
    )
    if targets_config:
        initialize_target_repositories(origin_dir, targets_config=targets_config)
        sign_target_repositories(
            origin_dir, repo_name, keystore=KEYSTORE_PATH, pin_manager=pin_manager
        )

    # Yield the authentication repository object
    return AuthenticationRepository(origin_dir, repo_name)


def setup_repository_no_info_json(
    origin_dir: Path,
    repo_name: str,
    targets_config: list,
    is_test_repo: bool,
    pin_manager: PinManager,
) -> AuthenticationRepository:
    # Define the origin path

    # Execute the tasks directly
    create_repositories_json(origin_dir, repo_name, targets_config=targets_config)
    create_mirrors_json(origin_dir, repo_name)
    create_authentication_repository(
        origin_dir,
        pin_manager,
        repo_name,
        keys_description=KEYS_DESCRIPTION,
        is_test_repo=is_test_repo,
    )
    if targets_config:
        initialize_target_repositories(origin_dir, targets_config=targets_config)
        sign_target_repositories(
            origin_dir, repo_name, keystore=KEYSTORE_PATH, pin_manager=pin_manager
        )

    # Yield the authentication repository object
    return AuthenticationRepository(origin_dir, repo_name)


def setup_repository_mirrors_added_later(
    origin_dir: Path,
    repo_name: str,
    targets_config: list,
    is_test_repo: bool,
    pin_manager: PinManager,
) -> AuthenticationRepository:
    # Execute the tasks directly
    create_repositories_json(origin_dir, repo_name, targets_config=targets_config)
    create_info_json(origin_dir, repo_name)
    create_authentication_repository(
        origin_dir,
        pin_manager,
        repo_name,
        keys_description=KEYS_DESCRIPTION,
        is_test_repo=is_test_repo,
    )
    if targets_config:
        initialize_target_repositories(origin_dir, targets_config=targets_config)
        sign_target_repositories(
            origin_dir, repo_name, keystore=KEYSTORE_PATH, pin_manager=pin_manager
        )
    create_mirrors_json(origin_dir, repo_name)
    sign_target_files(
        origin_dir, repo_name, keystore=KEYSTORE_PATH, pin_manager=pin_manager
    )

    # Yield the authentication repository object
    return AuthenticationRepository(origin_dir, repo_name)


def setup_repository_repositories_and_mirrors_added_later(
    origin_dir: Path,
    repo_name: str,
    targets_config: list,
    is_test_repo: bool,
    pin_manager: PinManager,
) -> AuthenticationRepository:
    # Execute the tasks directly
    create_info_json(origin_dir, repo_name)
    create_authentication_repository(
        origin_dir,
        pin_manager,
        repo_name,
        keys_description=KEYS_DESCRIPTION,
        is_test_repo=is_test_repo,
    )
    create_repositories_json(origin_dir, repo_name, targets_config=targets_config)
    create_mirrors_json(origin_dir, repo_name)
    sign_target_files(
        origin_dir, repo_name, keystore=KEYSTORE_PATH, pin_manager=pin_manager
    )
    if targets_config:
        initialize_target_repositories(origin_dir, targets_config=targets_config)
        sign_target_repositories(
            origin_dir, repo_name, keystore=KEYSTORE_PATH, pin_manager=pin_manager
        )

    # Yield the authentication repository object
    return AuthenticationRepository(origin_dir, repo_name)


def setup_repository_no_target_repositories(
    origin_dir: Path,
    repo_name: str,
    targets_config: list,
    is_test_repo: bool,
    pin_manager: PinManager,
) -> AuthenticationRepository:

    # Execute the tasks directly
    create_info_json(origin_dir, repo_name)
    create_repositories_json(origin_dir, repo_name, targets_config=targets_config)
    create_mirrors_json(origin_dir, repo_name)
    create_authentication_repository(
        origin_dir,
        pin_manager,
        repo_name,
        keys_description=KEYS_DESCRIPTION,
        is_test_repo=is_test_repo,
    )

    # Yield the authentication repository object
    return AuthenticationRepository(origin_dir, repo_name)


def add_file_to_repository(
    target_repo: GitRepository, filename: str, commit_message: Optional[str] = None
):
    content = _generate_random_text()
    file_path = target_repo.path / filename
    file_path.write_text(content)
    if commit_message is not None:
        target_repo.commit(commit_message)


def add_valid_target_commits(
    auth_repo: AuthenticationRepository,
    pin_manager: PinManager,
    target_repos: list,
    add_if_empty: bool = True,
):
    for target_repo in target_repos:
        if not add_if_empty and target_repo.head_commit() is None:
            continue
        update_target_repository(target_repo, "Update target files")
    sign_target_repositories(
        TEST_DATA_ORIGIN_PATH, auth_repo.name, KEYSTORE_PATH, pin_manager
    )


def add_file_to_target_repo_without_committing(target_repos: list, target_name: str):
    for target_repo in target_repos:
        if target_name in target_repo.name:
            add_file_to_repository(target_repo, "dirty.txt")


def add_file_to_auth_repo_without_committing(auth_repo: AuthenticationRepository):
    add_file_to_repository(auth_repo, "dirty.txt")


def add_valid_unauthenticated_commits(target_repos: list):
    for target_repo in target_repos:
        if target_repo.custom.get("allow-unauthenticated-commits", False):
            update_target_repository(target_repo, "Update target files")


def add_unauthenticated_commits_to_all_target_repos(target_repos: list):
    for target_repo in target_repos:
        update_target_repository(target_repo, "Update target files")


def add_unauthenticated_commit_to_target_repo(target_repos: list, target_name: str):
    for target_repo in target_repos:
        if target_name in target_repo.name:
            update_target_repository(target_repo, "Update target files")


def create_new_target_orphan_branches(
    auth_repo: AuthenticationRepository,
    target_repos: list,
    pin_manager: PinManager,
    branch_name: str,
):
    for target_repo in target_repos:
        target_repo.checkout_orphan_branch(branch_name)

        # create some files, content of these repositories is not important
        for i in range(1, 3):
            random_text = _generate_random_text()
            (target_repo.path / f"test{i}.txt").write_text(random_text)
        target_repo.commit("Initial commit")
    sign_target_repositories(
        TEST_DATA_ORIGIN_PATH, auth_repo.name, KEYSTORE_PATH, pin_manager
    )


def create_new_target_repo_branch(
    auth_repo: AuthenticationRepository, target_repos: list, target_name: str
):
    for repo in target_repos:
        if target_name in repo.name:
            branch_name = str(uuid.uuid4())
            repo.checkout_branch(branch_name, create=True)
            repo.commit_empty("Add new branch commit")
            break


def create_index_lock(auth_repo: AuthenticationRepository, client_dir: Path):
    # Create an `index.lock` file, indicating that an incomplete git operation took place
    # index.lock is created by git when a git operation is interrupted.
    target_repos = load_target_repositories(auth_repo)

    for target_repo in target_repos.values():
        index_lock = Path(client_dir, target_repo.name, ".git", "index.lock")
        index_lock.touch()
        break


def _generate_random_text(length=10):
    letters = string.ascii_letters
    return "".join(random.choice(letters) for i in range(length))


def remove_commits_from_auth_repo(
    auth_repo: AuthenticationRepository, num_of_commits: int = 1
):
    auth_repo.reset_num_of_commits(num_of_commits, hard=True)


def reset_to_commit(auth_repo: AuthenticationRepository, commit: Commitish):
    auth_repo.reset_to_commit(commit, hard=True)


def remove_last_validated_commit(auth_repo: AuthenticationRepository):
    Path(auth_repo.conf_dir, auth_repo.LAST_VALIDATED_FILENAME).unlink()
    assert auth_repo.last_validated_commit is None


def remove_last_validated_data(auth_repo: AuthenticationRepository):
    Path(auth_repo.conf_dir, auth_repo.LAST_VALIDATED_FILENAME).unlink()
    assert not auth_repo.last_validated_data


def replace_with_old_last_validated_commit_format(auth_repo: AuthenticationRepository):
    last_validated_commit = auth_repo.last_validated_commit or ""
    Path(auth_repo.conf_dir, auth_repo.LAST_VALIDATED_FILENAME).write_text(
        last_validated_commit
    )


def revert_last_validated_commit(auth_repo: AuthenticationRepository):
    older_commit = auth_repo.all_commits_on_branch(auth_repo.default_branch)[-2]
    auth_repo.set_last_validated_of_repo(
        auth_repo.name, older_commit, set_last_validated_commit=True
    )
    assert auth_repo.last_validated_commit == older_commit.hash


def set_last_commit_of_auth_repo(
    auth_repo: AuthenticationRepository, commit: Commitish
):
    auth_repo.set_last_validated_of_repo(
        auth_repo.name, commit, set_last_validated_commit=True
    )


def swap_last_two_commits(auth_repo: AuthenticationRepository):
    """
    Swap the top two commits of the currently checked out branch of the provided repo.
    This will not work in all cases (if there are modify/delete conflicts for instance)
    We can use it to swap commits of the authentication repository, but
    should not be moved into a git repository class
    """
    current_branch = auth_repo.get_current_branch()
    auth_repo._git("rebase -Xtheirs --onto HEAD~2 HEAD~1 HEAD")
    auth_repo._git("cherry-pick -Xtheirs ORIG_HEAD~1")
    auth_repo._git(
        "update-ref refs/heads/{} {}", current_branch, auth_repo.head_commit()
    )
    auth_repo._git("checkout --quiet {}", current_branch)


def update_expiration_dates(
    auth_repo: AuthenticationRepository,
    pin_manager: PinManager,
    roles=["snapshot", "timestamp"],
    push=True,
):
    update_metadata_expiration_date(
        str(auth_repo.path),
        pin_manager,
        roles=roles,
        keystore=KEYSTORE_PATH,
        interval=None,
        push=push,
    )


def update_auth_repo_without_committing(
    auth_repo: AuthenticationRepository, pin_manager, roles=["snapshot", "timestamp"]
):
    update_metadata_expiration_date(
        str(auth_repo.path),
        pin_manager,
        roles=roles,
        keystore=KEYSTORE_PATH,
        interval=None,
        commit=False,
    )


def update_role_metadata_without_signing(
    auth_repo: AuthenticationRepository, pin_manager, role: str
):
    update_metadata_expiration_date(
        path=auth_repo.path,
        pin_manager=pin_manager,
        roles=[role],
        keystore=KEYSTORE_PATH,
        prompt_for_keys=False,
        commit=False,
        push=False,
        update_snapshot_and_timestamp=False,
    )


def update_target_repo_without_committing(target_repos: list, target_name: str):
    for target_repo in target_repos:
        if target_name in target_repo.name:
            update_target_repository(target_repo, None)


def update_timestamp_metadata_invalid_signature(
    auth_repo: AuthenticationRepository,
):

    role = Timestamp.type
    with manage_repo_and_signers(
        auth_repo,
        [role],
        keystore=KEYSTORE_PATH,
        scheme=DEFAULT_RSA_SIGNATURE_SCHEME,
        prompt_for_keys=False,
        load_snapshot_and_timestamp=False,
        commit=True,
        commit_msg="Invalid metadata update",
        push=False,
    ):
        role_metadata_path = Path(auth_repo.path, "metadata", f"{role}.json")
        content = json.loads(role_metadata_path.read_text())
        content["signatures"][0]["sig"] = "invalid signature"
        version = content["signed"]["version"]
        content["signed"]["version"] = version + 1
        role_metadata_path.write_text(json.dumps(content, indent=1))


def update_and_sign_metadata_without_clean_check(
    auth_repo: AuthenticationRepository, pin_manager: PinManager, roles: list
):

    update_metadata_expiration_date(
        path=auth_repo.path,
        pin_manager=pin_manager,
        roles=roles,
        keystore=KEYSTORE_PATH,
        scheme=DEFAULT_RSA_SIGNATURE_SCHEME,
        prompt_for_keys=False,
        skip_clean_check=True,
        update_snapshot_and_timestamp=True,
    )


def update_target_repository(
    target_repo: GitRepository, commit_message: Optional[str] = None
):
    text_to_add = _generate_random_text()
    # Iterate over all files in the repository directory
    is_empty = True
    for file_path in target_repo.path.iterdir():
        if file_path.is_file():
            is_empty = False
            existing_content = file_path.read_text(encoding="utf-8")
            new_content = existing_content + "\n" + text_to_add
            file_path.write_text(new_content, encoding="utf-8")

    if is_empty:
        random_text = _generate_random_text()
        (target_repo.path / "test.txt").write_text(random_text)

    if commit_message is not None:
        target_repo.commit(commit_message)


def remove_commits(
    repo_path: str,
    num_commits: int = 1,
):
    repo = GitRepository(path=Path(repo_path))

    try:
        repo.reset_num_of_commits(num_commits, hard=True)
    except GitError as e:
        print(f"{str(e)}")


def checkout_detached_head(repo_path: str):
    """Checks out the repository to a detached HEAD state."""
    repo = GitRepository(path=Path(repo_path))
    head_commit_sha = repo.head_commit()
    if head_commit_sha:
        repo.checkout_commit(head_commit_sha)


def create_index_lock_in_repo(repo_path: str):
    """Creates an index.lock file to simulate an interrupted git operation."""
    repo = GitRepository(path=Path(repo_path))
    index_lock_path = repo.path / ".git" / "index.lock"
    index_lock_path.touch()


def set_head_commit(auth_repo: AuthenticationRepository):
    last_valid_commit = auth_repo.head_commit()
    if last_valid_commit is not None:
        auth_repo.set_last_validated_of_repo(
            auth_repo.name, last_valid_commit, set_last_validated_commit=True
        )
    else:
        raise ValueError("Failed to retrieve the last valid commit SHA.")


def pull_specific_target_repo(
    auth_repo: AuthenticationRepository, target_repos: list, repo_path: str
):
    client_target_repo = GitRepository(path=repo_path)
    client_target_repo.pull()
    return


def pull_all_target_repos(auth_repo: AuthenticationRepository, client_dir: Path):
    client_target_repos = load_target_repositories(auth_repo, library_dir=client_dir)
    for _, client_repo in client_target_repos.items():
        client_repo.pull()


def pull_client_auth_repo(auth_repo: AuthenticationRepository, client_dir: Path):
    client_auth_repo = AuthenticationRepository(client_dir, auth_repo.name)
    client_auth_repo.pull()
