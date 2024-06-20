import re
import pytest
import inspect
import random
import shutil
import string
import json
from functools import partial
from freezegun import freeze_time
from pathlib import Path
from jinja2 import Environment, BaseLoader
from taf.api.metadata import (
    _update_expiration_date_of_role,
    update_metadata_expiration_date,
)
from taf.auth_repo import AuthenticationRepository
from taf.constants import DEFAULT_RSA_SIGNATURE_SCHEME
from taf.messages import git_commit_message
from taf import repositoriesdb
from taf.utils import on_rm_error
from taf.tests.test_updater.update_utils import load_target_repositories
from tuf.repository_tool import TARGETS_DIRECTORY_NAME
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
from taf.tests.conftest import (
    CLIENT_DIR_PATH,
    TEST_DATA_ORIGIN_PATH,
    KEYSTORE_PATH,
    TEST_INIT_DATA_PATH,
)
from taf.api.utils._git import commit_and_push


KEYS_DESCRIPTION = str(TEST_INIT_DATA_PATH / "keys.json")


TARGET_MISSMATCH_PATTERN = r"Update of (\w+)\/(\w+) failed due to error: Failure to validate (\w+)\/(\w+) commit ([0-9a-f]{40}) committed on (\d{4}-\d{2}-\d{2}): data repository ([\w\/-]+) was supposed to be at commit ([0-9a-z]{40}) but repo was at ([0-9a-f]{40})"
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
NO_INFO_JSON = f"Update of repository failed due to error: Error during info.json parse. If the authentication repository's path is not specified, info.json metadata is expected to be in targets/protected"
UNCOIMITTED_CHANGES = r"Update of (\w+\/\w+) failed due to error: Repository (\w+\/\w+) should contain only committed changes\. \nPlease update the repository at (.+) manually and try again\."


class Task:
    def __init__(self, function, date, repetitions, params):
        self.function = function
        self.params = params
        self.date = date
        self.repetitions = repetitions


class SetupManager:
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
        repositoriesdb.clear_repositories_db()


class RepositoryConfig:
    def __init__(self, name, allow_unauthenticated_commits=False):
        self.name = name
        self.allow_unauthenticated_commits = allow_unauthenticated_commits


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
def origin_auth_repo(request, test_name):
    targets_config_list = request.param["targets_config"]
    is_test_repo = request.param.get("is_test_repo", False)
    date = request.param.get("data")
    setup_type = request.param.get("setup_type", "all_files_initially")
    targets_config = [
        RepositoryConfig(
            f"{test_name}/{targets_config['name']}",
            targets_config.get("allow_unauthenticated_commits", False),
        )
        for targets_config in targets_config_list
    ]
    repo_name = f"{test_name}/auth"

    client_path = CLIENT_DIR_PATH / test_name
    origin_path = TEST_DATA_ORIGIN_PATH / test_name
    shutil.rmtree(origin_path, onerror=on_rm_error)
    shutil.rmtree(client_path, onerror=on_rm_error)

    if date is not None:
        with freeze_time(date):
            auth_repo = _init_auth_repo(
                setup_type, repo_name, targets_config, is_test_repo
            )
    else:
        auth_repo = _init_auth_repo(setup_type, repo_name, targets_config, is_test_repo)

    yield auth_repo

    shutil.rmtree(origin_path, onerror=on_rm_error)
    shutil.rmtree(client_path, onerror=on_rm_error)


def clone_client_repo(target_name, origin_dir, client_dir):
    origin_repo_path = str(origin_dir / target_name)
    client_repo = GitRepository(client_dir, target_name)
    client_repo.clone_from_disk(origin_repo_path, keep_remote=True)
    return client_repo


def create_repositories_json(
    library_dir, repo_name, targets_config: list[RepositoryConfig]
):
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
    info_content = {
        "namespace": repo_name.split("/")[0],
        "name": repo_name.split("/")[1],
    }
    info_json_path.write_text(json.dumps(info_content))


def create_mirrors_json(library_dir, repo_name):
    repo_path = Path(library_dir, repo_name)
    targets_dir_path = repo_path / TARGETS_DIRECTORY_NAME
    targets_dir_path.mkdir(parents=True, exist_ok=True)
    mirrors = {"mirrors": [f"{library_dir}/{{org_name}}/{{repo_name}}"]}
    mirrors_path = targets_dir_path / MIRRORS_JSON_NAME
    mirrors_path.write_text(json.dumps(mirrors))


def create_authentication_repository(
    library_dir, repo_name, keys_description, is_test_repo=False
):
    repo_path = Path(library_dir, repo_name)
    create_repository(
        str(repo_path),
        str(KEYSTORE_PATH),
        keys_description,
        commit=True,
        test=is_test_repo,
    )


def sign_target_files(library_dir, repo_name, keystore):
    repo_path = Path(library_dir, repo_name)
    register_target_files(str(repo_path), keystore, write=True)


def _init_auth_repo(setup_type, repo_name, targets_config, is_test_repo):
    if setup_type == "all_files_initially":
        return setup_repository_all_files_initially(
            repo_name, targets_config, is_test_repo
        )
    elif setup_type == "no_info_json":
        return setup_repository_no_info_json(repo_name, targets_config, is_test_repo)
    elif setup_type == "mirrors_added_later":
        return setup_repository_mirrors_added_later(
            repo_name, targets_config, is_test_repo
        )
    elif setup_type == "repositories_and_mirrors_added_later":
        return setup_repository_repositories_and_mirrors_added_later(
            repo_name, targets_config, is_test_repo
        )
    elif setup_type == "no_target_repositories":
        return setup_repository_no_target_repositories(
            repo_name, targets_config, is_test_repo
        )
    else:
        raise ValueError(f"Unsupported setup type: {setup_type}")


def initialize_git_repo(library_dir: Path, repo_name: str):
    repo_path = Path(library_dir, repo_name)
    repo_path.mkdir(parents=True, exist_ok=True)
    repo = GitRepository(path=repo_path)
    repo.init_repo()
    return repo


def initialize_target_repositories(
    library_dir, repo_name, targets_config: list, create_new_repo=True
):
    for target_config in targets_config:
        if create_new_repo:
            target_repo = initialize_git_repo(
                library_dir=library_dir, repo_name=target_config.name
            )
        else:
            target_repo = GitRepository(library_dir, target_config.name)
        # create some files, content of these repositories is not important
        for i in range(1, 3):
            random_text = _generate_random_text()
            (target_repo.path / f"test{i}.txt").write_text(random_text)
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


def setup_repository_all_files_initially(repo_name, targets_config, is_test_repo):
    # Define the origin path
    origin_path = TEST_DATA_ORIGIN_PATH

    # Execute the tasks directly
    create_repositories_json(origin_path, repo_name, targets_config=targets_config)
    create_mirrors_json(origin_path, repo_name)
    create_info_json(origin_path, repo_name)
    create_authentication_repository(
        origin_path,
        repo_name,
        keys_description=KEYS_DESCRIPTION,
        is_test_repo=is_test_repo,
    )
    initialize_target_repositories(
        origin_path, repo_name, targets_config=targets_config
    )
    sign_target_repositories(origin_path, repo_name, keystore=KEYSTORE_PATH)

    # Yield the authentication repository object
    return AuthenticationRepository(origin_path, repo_name)


def setup_repository_no_info_json(repo_name, targets_config, is_test_repo):
    # Define the origin path
    origin_path = TEST_DATA_ORIGIN_PATH

    # Execute the tasks directly
    create_repositories_json(origin_path, repo_name, targets_config=targets_config)
    create_mirrors_json(origin_path, repo_name)
    create_authentication_repository(
        origin_path,
        repo_name,
        keys_description=KEYS_DESCRIPTION,
        is_test_repo=is_test_repo,
    )
    initialize_target_repositories(
        origin_path, repo_name, targets_config=targets_config
    )
    sign_target_repositories(origin_path, repo_name, keystore=KEYSTORE_PATH)

    # Yield the authentication repository object
    return AuthenticationRepository(origin_path, repo_name)


def setup_repository_mirrors_added_later(repo_name, targets_config, is_test_repo):
    # Define the origin path
    origin_path = TEST_DATA_ORIGIN_PATH

    # Execute the tasks directly
    create_repositories_json(origin_path, repo_name, targets_config=targets_config)
    create_info_json(origin_path, repo_name)
    create_authentication_repository(
        origin_path,
        repo_name,
        keys_description=KEYS_DESCRIPTION,
        is_test_repo=is_test_repo,
    )
    initialize_target_repositories(
        origin_path, repo_name, targets_config=targets_config
    )
    sign_target_repositories(origin_path, repo_name, keystore=KEYSTORE_PATH)
    create_mirrors_json(origin_path, repo_name)
    sign_target_files(origin_path, repo_name, keystore=KEYSTORE_PATH)

    # Yield the authentication repository object
    return AuthenticationRepository(origin_path, repo_name)


def setup_repository_repositories_and_mirrors_added_later(
    repo_name, targets_config, is_test_repo
):
    # Define the origin path
    origin_path = TEST_DATA_ORIGIN_PATH

    # Execute the tasks directly
    create_info_json(origin_path, repo_name)
    create_authentication_repository(
        origin_path,
        repo_name,
        keys_description=KEYS_DESCRIPTION,
        is_test_repo=is_test_repo,
    )
    create_repositories_json(origin_path, repo_name, targets_config=targets_config)
    create_mirrors_json(origin_path, repo_name)
    sign_target_files(origin_path, repo_name, keystore=KEYSTORE_PATH)
    initialize_target_repositories(
        origin_path, repo_name, targets_config=targets_config
    )
    sign_target_repositories(origin_path, repo_name, keystore=KEYSTORE_PATH)

    # Yield the authentication repository object
    return AuthenticationRepository(origin_path, repo_name)


def setup_repository_no_target_repositories(repo_name, targets_config, is_test_repo):
    # Define the origin path
    origin_path = TEST_DATA_ORIGIN_PATH

    # Execute the tasks directly
    create_info_json(origin_path, repo_name)
    create_repositories_json(origin_path, repo_name, targets_config=targets_config)
    create_mirrors_json(origin_path, repo_name)
    create_authentication_repository(
        origin_path,
        repo_name,
        keys_description=KEYS_DESCRIPTION,
        is_test_repo=is_test_repo,
    )

    # Yield the authentication repository object
    return AuthenticationRepository(origin_path, repo_name)


def add_valid_target_commits(auth_repo, target_repos):
    for target_repo in target_repos:
        update_target_files(target_repo, "Update target files")
    sign_target_repositories(TEST_DATA_ORIGIN_PATH, auth_repo.name, KEYSTORE_PATH)


def add_valid_unauthenticated_commits(target_repos):
    for target_repo in target_repos:
        if target_repo.custom.get("allow-unauthenticated-commits", False):
            update_target_files(target_repo, "Update target files")


def add_unauthenticated_commits_to_all_target_repos(target_repos):
    for target_repo in target_repos:
        update_target_files(target_repo, "Update target files")


def create_new_target_orphan_branches(auth_repo, target_repos, branch_name):
    for target_repo in target_repos:
        target_repo.checkout_orphan_branch(branch_name)

        # create some files, content of these repositories is not important
        for i in range(1, 3):
            random_text = _generate_random_text()
            (target_repo.path / f"test{i}.txt").write_text(random_text)
        target_repo.commit("Initial commit")
    sign_target_repositories(TEST_DATA_ORIGIN_PATH, auth_repo.name, KEYSTORE_PATH)


def create_index_lock(auth_repo, client_dir):
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


def remove_last_validate_commit(auth_repo, client_dir):
    client_repo = AuthenticationRepository(client_dir, auth_repo.name)
    Path(client_repo.conf_dir, client_repo.LAST_VALIDATED_FILENAME).unlink()
    assert client_repo.last_validated_commit is None


def revert_last_validated_commit(auth_repo, client_dir):
    client_repo = AuthenticationRepository(client_dir, auth_repo.name)
    older_commit = client_repo.all_commits_on_branch(client_repo.default_branch)[-2]
    client_repo.set_last_validated_commit(older_commit)
    assert client_repo.last_validated_commit == older_commit


def swap_last_two_commits(auth_repo):
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
        "update-ref refs/heads/{} {}", current_branch, auth_repo.head_commit_sha()
    )
    auth_repo._git("checkout --quiet {}", current_branch)


def update_expiration_dates(auth_repo, roles=["snapshot", "timestamp"]):
    update_metadata_expiration_date(
        str(auth_repo.path), roles=roles, keystore=KEYSTORE_PATH, interval=None
    )


def update_role_metadata_without_signing(auth_repo, role):
    _update_expiration_date_of_role(
        auth_repo=auth_repo,
        role=role,
        loaded_yubikeys={},
        start_date=None,
        keystore=KEYSTORE_PATH,
        interval=None,
        scheme=DEFAULT_RSA_SIGNATURE_SCHEME,
        prompt_for_keys=False,
    )


def update_role_metadata_invalid_signature(auth_repo, role):
    role_metadata_path = Path(auth_repo.path, "metadata", f"{role}.json")
    content = json.loads(role_metadata_path.read_text())
    content["signatures"][0]["sign"] = "invalid signature"
    version = content["signed"]["version"]
    content["signed"]["version"] = version + 1
    role_metadata_path.write_text(json.dumps(content))
    auth_repo.commit("Invalid metadata update")


def update_and_sign_metadata_without_clean_check(auth_repo, roles):
    if "root" or "targets" in roles:
        if "snapshot" not in roles:
            roles.append("snapshot")
        if "timestamp" not in roles:
            roles.append("timestamp")

    roles = ["root", "snapshot", "timestamp"]
    for role in roles:
        _update_expiration_date_of_role(
            auth_repo=auth_repo,
            role=role,
            loaded_yubikeys={},
            start_date=None,
            keystore=KEYSTORE_PATH,
            interval=None,
            scheme=DEFAULT_RSA_SIGNATURE_SCHEME,
            prompt_for_keys=False,
        )

    commit_msg = git_commit_message("update-expiration-dates", roles=",".join(roles))
    commit_and_push(auth_repo, commit_msg=commit_msg, push=False)


def update_target_files(target_repo, commit_message):
    text_to_add = _generate_random_text()
    # Iterate over all files in the repository directory
    for file_path in target_repo.path.iterdir():
        if file_path.is_file():
            existing_content = file_path.read_text(encoding="utf-8")
            new_content = existing_content + "\n" + text_to_add
            file_path.write_text(new_content, encoding="utf-8")
    target_repo.commit(commit_message)
