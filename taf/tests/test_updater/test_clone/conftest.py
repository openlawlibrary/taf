import re
import shutil
import pytest
from freezegun import freeze_time
from taf.tests.conftest import CLIENT_DIR_PATH, TEST_DATA_ORIGIN_PATH
from taf.tests.test_updater.conftest import (
    RepositoryConfig,
    add_unauthenticated_commits,
    add_valid_target_commits,
    apply_update_instructions,
    create_new_target_orphan_branches,
    setup_base_repositories,
    update_and_sign_metadata_without_clean_check,
    update_expiration_dates,
    update_role_metadata_without_signing,
)
from taf.utils import on_rm_error


@pytest.fixture
def excluded_target_globs(request):
    return request.param


@pytest.fixture
def existing_target_repositories(request):
    return request.param


@pytest.fixture(scope="function")
def test_name(request):
    # Extract the test name and the counter
    match = re.match(r"(.+)\[.+(\d+)\]", request.node.name)
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
    targets_config = [
        RepositoryConfig(
            f"{test_name}/{targets_config['name']}",
            targets_config.get("allow_unauthenticated_commits", False),
        )
        for targets_config in targets_config_list
    ]
    repo_name = f"{test_name}/auth"
    update_instructions = request.param.get("update_instructions", [])

    if date is not None:
        with freeze_time(date):
            auth_repo = setup_base_repositories(repo_name, targets_config, is_test_repo)
    else:
        auth_repo = setup_base_repositories(repo_name, targets_config, is_test_repo)

    apply_update_instructions(auth_repo, update_instructions, targets_config)
    yield auth_repo

    namespace = repo_name.split("/")[0]
    client_path = CLIENT_DIR_PATH / namespace
    origin_path = TEST_DATA_ORIGIN_PATH / namespace
    shutil.rmtree(origin_path, onerror=on_rm_error)
    shutil.rmtree(client_path, onerror=on_rm_error)
