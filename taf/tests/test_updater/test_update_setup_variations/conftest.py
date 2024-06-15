import pytest
import shutil
from taf.auth_repo import AuthenticationRepository
from taf.tests.conftest import CLIENT_DIR_PATH, KEYSTORE_PATH, TEST_DATA_ORIGIN_PATH
from taf.tests.test_updater.conftest import (
    KEYS_DESCRIPTION,
    RepositoryConfig,
    TaskManager,
    create_authentication_repository,
    create_info_json,
    create_mirrors_json,
    create_repositories_json,
    initialize_target_repositories,
    sign_target_files,
    sign_target_repositories,
)
from taf.utils import on_rm_error


@pytest.fixture(scope="function")
def origin_auth_repo(request):
    setup_type = request.param["setup_type"]
    targets_config_list = request.param["targets_config"]
    is_test_repo = request.param.get("is_test_repo", False)
    targets_config = [
        RepositoryConfig(
            f"{setup_type}/{targets_config['name']}",
            targets_config.get("allow_unauthenticated_commits", False),
        )
        for targets_config in targets_config_list
    ]
    repo_name = f"{setup_type}/auth"
    if setup_type == "all_files_initially":
        yield from setup_repository_all_files_initially(
            repo_name, targets_config, is_test_repo
        )
    elif setup_type == "no_info_json":
        yield from setup_repository_no_info_json(
            repo_name, targets_config, is_test_repo
        )
    elif setup_type == "mirrors_added_later":
        yield from setup_repository_mirrors_added_later(
            repo_name, targets_config, is_test_repo
        )
    elif setup_type == "repositories_and_mirrors_added_later":
        yield from setup_repository_repositories_and_mirrors_added_later(
            repo_name, targets_config, is_test_repo
        )
    elif setup_type == "no_target_repositories":
        yield from setup_repository_no_target_repositories(
            repo_name, targets_config, is_test_repo
        )
    else:
        raise ValueError(f"Unsupported setup type: {setup_type}")

    namespace = repo_name.split("/")[0]
    client_path = CLIENT_DIR_PATH / namespace
    origin_path = TEST_DATA_ORIGIN_PATH / namespace
    shutil.rmtree(origin_path, onerror=on_rm_error)
    shutil.rmtree(client_path, onerror=on_rm_error)


def setup_repository_all_files_initially(repo_name, targets_config, is_test_repo):
    setup_manager = TaskManager(TEST_DATA_ORIGIN_PATH, repo_name)
    setup_manager.add_task(
        create_repositories_json, [{"targets_config": targets_config}]
    )
    setup_manager.add_task(create_mirrors_json)
    setup_manager.add_task(create_info_json)
    setup_manager.add_task(
        create_authentication_repository,
        [{"keys_description": KEYS_DESCRIPTION, "is_test_repo": is_test_repo}],
    )
    setup_manager.add_task(
        initialize_target_repositories, [{"targets_config": targets_config}]
    )
    setup_manager.add_task(sign_target_repositories, [{"keystore": KEYSTORE_PATH}])
    setup_manager.run_tasks()
    auth_repo = AuthenticationRepository(TEST_DATA_ORIGIN_PATH, repo_name)
    yield auth_repo


def setup_repository_no_info_json(repo_name, targets_config, is_test_repo):

    setup_manager = TaskManager(TEST_DATA_ORIGIN_PATH, repo_name)
    setup_manager.add_task(
        create_repositories_json, [{"targets_config": targets_config}]
    )
    setup_manager.add_task(create_mirrors_json)
    setup_manager.add_task(
        create_authentication_repository,
        [{"keys_description": KEYS_DESCRIPTION, "is_test_repo": is_test_repo}],
    )
    setup_manager.add_task(
        initialize_target_repositories, [{"targets_config": targets_config}]
    )
    setup_manager.add_task(sign_target_repositories, [{"keystore": KEYSTORE_PATH}])
    setup_manager.run_tasks()

    auth_repo = AuthenticationRepository(TEST_DATA_ORIGIN_PATH, repo_name)
    yield auth_repo


def setup_repository_mirrors_added_later(repo_name, targets_config, is_test_repo):

    setup_manager = TaskManager(TEST_DATA_ORIGIN_PATH, repo_name)
    setup_manager.add_task(
        create_repositories_json, [{"targets_config": targets_config}]
    )
    setup_manager.add_task(create_info_json)
    setup_manager.add_task(
        create_authentication_repository,
        [{"keys_description": KEYS_DESCRIPTION, "is_test_repo": is_test_repo}],
    )
    setup_manager.add_task(
        initialize_target_repositories, [{"targets_config": targets_config}]
    )
    setup_manager.add_task(sign_target_repositories, [{"keystore": KEYSTORE_PATH}])
    setup_manager.add_task(
        [create_mirrors_json, sign_target_files], [{}, {"keystore": KEYSTORE_PATH}]
    )
    setup_manager.run_tasks()

    auth_repo = AuthenticationRepository(TEST_DATA_ORIGIN_PATH, repo_name)
    yield auth_repo


def setup_repository_repositories_and_mirrors_added_later(
    repo_name, targets_config, is_test_repo
):

    setup_manager = TaskManager(TEST_DATA_ORIGIN_PATH, repo_name)
    setup_manager.add_task(create_info_json)
    setup_manager.add_task(
        create_authentication_repository,
        [{"keys_description": KEYS_DESCRIPTION, "is_test_repo": is_test_repo}],
    )
    setup_manager.add_task(
        [create_repositories_json, create_mirrors_json, sign_target_files],
        [{"targets_config": targets_config}, {}, {"keystore": KEYSTORE_PATH}],
    )
    setup_manager.add_task(
        initialize_target_repositories, [{"targets_config": targets_config}]
    )
    setup_manager.add_task(sign_target_repositories, [{"keystore": KEYSTORE_PATH}])
    setup_manager.run_tasks()

    auth_repo = AuthenticationRepository(TEST_DATA_ORIGIN_PATH, repo_name)
    yield auth_repo


def setup_repository_no_target_repositories(repo_name, targets_config, is_test_repo):

    setup_manager = TaskManager(TEST_DATA_ORIGIN_PATH, repo_name)
    setup_manager.add_task(create_info_json)
    setup_manager.add_task(
        create_repositories_json, [{"targets_config": targets_config}]
    )
    setup_manager.add_task(create_mirrors_json)
    setup_manager.add_task(
        create_authentication_repository,
        [{"keys_description": KEYS_DESCRIPTION, "is_test_repo": is_test_repo}],
    )
    setup_manager.run_tasks()

    auth_repo = AuthenticationRepository(TEST_DATA_ORIGIN_PATH, repo_name)
    yield auth_repo
