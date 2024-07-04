import re
from taf.repositoriesdb import (
    DEPENDENCIES_JSON_NAME,
)
from taf.tests.test_updater.update_utils import load_target_repositories
from taf.tests.test_updater.conftest import (
    RepositoryConfig,
    setup_repository_all_files_initially,
    sign_target_files,
)
from taf.tests.conftest import (
    KEYSTORE_PATH,
    TEST_INIT_DATA_PATH,
)
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


def create_and_write_json(template_path, substitutions, output_path):
    template = template_path.read_text()
    for key, value in substitutions.items():
        template = re.sub(rf"\{{{key}\}}", value, template)
    output_path.write_text(template)


@fixture
def library_with_dependencies(origin_dir):
    library = {}

    namespaces = [NAMESPACE1, NAMESPACE2]

    initial_commits = []
    for namespace in namespaces:
        targets_config = [
            RepositoryConfig(f"{namespace}/{TARGET1_NAME}"),
            RepositoryConfig(f"{namespace}/{TARGET2_NAME}"),
        ]
        repo_name = f"{namespace}/auth"
        auth_repo = setup_repository_all_files_initially(
            origin_dir, repo_name, targets_config, False
        )
        target_repos = load_target_repositories(auth_repo).values()
        library[auth_repo.name] = {"auth_repo": auth_repo, "target_repos": target_repos}
        initial_commits.append(
            auth_repo.get_first_commit_on_branch(auth_repo.default_branch)
        )

    root_repo_name = f"{ROOT_REPO_NAMESPACE}/auth"
    root_auth_repo = setup_repository_all_files_initially(
        origin_dir, root_repo_name, {}, False
    )
    (root_auth_repo.path / TARGETS_DIRECTORY_NAME).mkdir(parents=True, exist_ok=True)
    create_and_write_json(
        TEST_INIT_DATA_PATH / DEPENDENCIES_JSON_NAME,
        {"commit1": initial_commits[0], "commit2": initial_commits[1]},
        root_auth_repo.path / TARGETS_DIRECTORY_NAME / DEPENDENCIES_JSON_NAME,
    )
    sign_target_files(origin_dir, root_repo_name, keystore=KEYSTORE_PATH)

    library[root_auth_repo.name] = {"auth_repo": root_auth_repo, "target_repos": []}

    yield library
