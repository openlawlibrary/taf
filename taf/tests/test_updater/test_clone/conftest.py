import re
import shutil
import pytest
from freezegun import freeze_time
from taf.tests.conftest import CLIENT_DIR_PATH, TEST_DATA_ORIGIN_PATH
from taf.tests.test_updater.conftest import (
    RepositoryConfig,
    add_unauthenticated_commits,
    add_valid_target_commits,
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

    # Apply updates
    for instruction in update_instructions:
        action = instruction.get("action")
        params = instruction.get("params", {})
        date = params.get("date")
        number = params.get("number", 1)

        if date is not None:
            with freeze_time(date):
                _execute_action(action, auth_repo, targets_config, params, number)
        else:
            _execute_action(action, auth_repo, targets_config, params, number)

    yield auth_repo

    namespace = repo_name.split("/")[0]
    client_path = CLIENT_DIR_PATH / namespace
    origin_path = TEST_DATA_ORIGIN_PATH / namespace
    shutil.rmtree(origin_path, onerror=on_rm_error)
    shutil.rmtree(client_path, onerror=on_rm_error)


def _execute_action(action, auth_repo, targets_config, params, number=1):
    for _ in range(number):
        if action == "add_valid_target_commits":
            add_valid_target_commits(auth_repo, targets_config)
        elif action == "update_expiration_dates":
            roles = params.get("roles", ["snapshot", "timestamp"])
            update_expiration_dates(auth_repo, roles=roles)
        elif action == "add_unauthenticated_commits":
            add_unauthenticated_commits(auth_repo, targets_config)
        elif action == "create_new_target_orphan_branches":
            branch_name = params["branch_name"]
            create_new_target_orphan_branches(auth_repo, targets_config, branch_name)
        elif action == "update_role_metadata_without_signing":
            role = params["role"]
            update_role_metadata_without_signing(auth_repo, role)
        elif action == "update_and_sign_metadata_without_clean_check":
            roles = params["roles"]
            update_and_sign_metadata_without_clean_check(auth_repo, roles)
        else:
            raise ValueError(f"Unknown action: {action}")
