import json
import re
from taf.api.repository import create_repository
from taf.api.targets import update_target_repos_from_repositories_json
from taf.git import GitRepository
from taf.tests.conftest import CLIENT_DIR_PATH, KEYSTORE_PATH, TEST_INIT_DATA_PATH, origin_repos_group
from tuf.ngclient._internal import trusted_metadata_set
from pytest import fixture

original_tuf_trusted_metadata_set = trusted_metadata_set.TrustedMetadataSet

NAMESPACE1 = "namespace1"
NAMESPACE2 = "namespace2"
TARGET1_NAME = "target1"
TARGET2_NAME = "target2"
TARGET3_NAME = "target3"
AUTH_NAME = "auth"


@fixture(scope="session", autouse=True)
def updater_repositories():
    test_dir = "test-updater"
    with origin_repos_group(test_dir) as origins:
        yield origins


def _initialize_target_repo(namespace, repo_name):
    repo_path = CLIENT_DIR_PATH / namespace / repo_name
    repo_path.mkdir(parents=True, exist_ok=True)
    repo = GitRepository(path=repo_path)
    repo.init_repo()
    # create some files
    (repo_path / "test1.txt").write_text("Test file 1")
    (repo_path / "test2.txt").write_text("Test file 2")
    repo.commit("Initial commit")
    return repo


@fixture
def library():

    library = {}

    namespaces = [NAMESPACE1, NAMESPACE2]
    for namespace in namespaces:
        # Initialize auth repository for the namespace
        auth_repo_path = CLIENT_DIR_PATH / namespace / AUTH_NAME
        auth_repo_path.mkdir(parents=True, exist_ok=True)
        auth_repo = GitRepository(path=auth_repo_path)
        auth_repo.init_repo()
        repositories_path_template = (TEST_INIT_DATA_PATH / "repositories.json").read_text()
        repositories_json_str = re.sub(r'\{namespace\}', namespace, repositories_path_template)
        repositories_json = json.loads(repositories_json_str)

        # Write repositories JSON to file
        targets_dir = auth_repo_path / "targets"
        targets_dir.mkdir(exist_ok=True)
        repositories_json_path = targets_dir / "repositories.json"
        repositories_json_path.write_text(json.dumps(repositories_json))

        # Create auth repository
        keys_description = str(TEST_INIT_DATA_PATH / "keys.json")
        create_repository(str(auth_repo_path), str(KEYSTORE_PATH), keys_description)
        auth_repo.commit("Initial commit")
        target_names = [TARGET1_NAME, TARGET2_NAME, TARGET3_NAME]
        target_repos = []

        target_repos = []
        for target_name in target_names:
            repo = _initialize_target_repo(namespace, target_name)
            target_repos.append(repo)
        update_target_repos_from_repositories_json(
            str(auth_repo_path), str(CLIENT_DIR_PATH), str(KEYSTORE_PATH),
        )
        library[auth_repo.name] = {
            "auth_repo": auth_repo,
            "target_repos": target_repos
        }

    yield library


CLIENT_DIR_PATH