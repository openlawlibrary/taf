import re
from taf.constants import TARGETS_DIRECTORY_NAME
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
def library_with_dependencies(origin_dir, pin_manager, request):
    library = {}
    dependencies_config = request.param["dependencies_config"]
    initial_commits = {}

    for dep in dependencies_config:
        namespace = dep["name"]
        targets_config = [
            RepositoryConfig(target["name"]) for target in dep.get("targets_config", [])
        ]
        auth_repo = setup_repository_all_files_initially(
            origin_dir, namespace, targets_config, False, pin_manager
        )
        target_repos = load_target_repositories(auth_repo).values()
        library[auth_repo.name] = {
            "auth_repo": auth_repo,
            "target_repos": list(target_repos),
        }
        initial_commits[namespace] = auth_repo.get_first_commit_on_branch(
            auth_repo.default_branch
        )

    root_repo_name = f"{ROOT_REPO_NAMESPACE}/{AUTH_NAME}"
    root_auth_repo = setup_repository_all_files_initially(
        origin_dir, root_repo_name, [], False, pin_manager
    )
    (root_auth_repo.path / TARGETS_DIRECTORY_NAME).mkdir(parents=True, exist_ok=True)

    params = {
        f"commit{i + 1}": commit.value
        for i, commit in enumerate(initial_commits.values())
    }
    params.update(
        {f"name{i + 1}": dep["name"] for i, dep in enumerate(dependencies_config)}
    ),
    create_and_write_json(
        TEST_INIT_DATA_PATH / DEPENDENCIES_JSON_NAME,
        params,
        root_auth_repo.path / TARGETS_DIRECTORY_NAME / DEPENDENCIES_JSON_NAME,
    )
    sign_target_files(
        origin_dir, root_repo_name, keystore=KEYSTORE_PATH, pin_manager=pin_manager
    )

    library[root_auth_repo.name] = {"auth_repo": root_auth_repo, "target_repos": []}
    yield library
