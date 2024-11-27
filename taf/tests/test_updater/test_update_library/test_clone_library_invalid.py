# test_update_library.py
import pytest
from taf.exceptions import UpdateFailedError
from taf.tests.test_updater.conftest import (
    INVALID_TIMESTAMP_PATTERN,
    INVALID_TIMESTAMP_PATTERN_ROOT,
    TARGET_MISMATCH_PATTERN_DEPENDENCIES,
    SetupManager,
    add_unauthenticated_commits_to_all_target_repos,
    add_valid_target_commits,
    update_timestamp_metadata_invalid_signature,
)
from taf.updater.types.update import UpdateType
from taf.tests.test_updater.update_utils import clone_full_library


@pytest.mark.parametrize(
    "library_with_dependencies",
    [
        {
            "targets_config": [{"name": "target1"}, {"name": "target2"}],
            "dependencies_config": [
                {
                    "name": "namespace1/auth",
                    "targets_config": [
                        {"name": "namespace1/target1"},
                        {"name": "namespace1/target2"},
                    ],
                },
                {
                    "name": "namespace2/auth",
                    "targets_config": [
                        {"name": "namespace2/target1"},
                        {"name": "namespace2/target2"},
                    ],
                },
                # Add additional dependencies as needed
            ],
        },
    ],
    indirect=True,
)
def test_clone_with_invalid_dependency_repo(
    library_with_dependencies, origin_dir, client_dir
):
    # Invalidate one of the authentication repositories in dependencies
    dependency_auth_repo = library_with_dependencies["namespace1/auth"]["auth_repo"]
    setup_manager = SetupManager(dependency_auth_repo)
    setup_manager.add_task(update_timestamp_metadata_invalid_signature)
    setup_manager.execute_tasks()

    # Run the updater which will clone and then update
    with pytest.raises(UpdateFailedError, match=INVALID_TIMESTAMP_PATTERN):
        clone_full_library(
            library_with_dependencies,
            origin_dir,
            client_dir,
            expected_repo_type=UpdateType.EITHER,
            excluded_target_globs=None,
        )


@pytest.mark.parametrize(
    "library_with_dependencies",
    [
        {
            "targets_config": [{"name": "target1"}, {"name": "target2"}],
            "dependencies_config": [
                {
                    "name": "namespace1/auth",
                    "targets_config": [
                        {"name": "namespace1/target1"},
                        {"name": "namespace1/target2"},
                    ],
                },
                {
                    "name": "namespace2/auth",
                    "targets_config": [
                        {"name": "namespace2/target1"},
                        {"name": "namespace2/target2"},
                    ],
                },
                # Add additional dependencies as needed
            ],
        },
    ],
    indirect=True,
)
def test_clone_invalid_target_repo(
    library_with_dependencies,
    origin_dir,
    client_dir,
):
    # Invalidate one of the target repositories
    auth_repo = library_with_dependencies["namespace1/auth"]["auth_repo"]
    setup_manager = SetupManager(auth_repo)
    setup_manager.add_task(add_valid_target_commits)
    setup_manager.add_task(add_unauthenticated_commits_to_all_target_repos)
    setup_manager.add_task(add_valid_target_commits)
    setup_manager.execute_tasks()
    # Run the updater which will clone and then update
    with pytest.raises(UpdateFailedError, match=TARGET_MISMATCH_PATTERN_DEPENDENCIES):
        clone_full_library(
            library_with_dependencies,
            origin_dir,
            client_dir,
            expected_repo_type=UpdateType.EITHER,
            excluded_target_globs=None,
        )


@pytest.mark.parametrize(
    "library_with_dependencies",
    [
        {
            "targets_config": [{"name": "target1"}, {"name": "target2"}],
            "dependencies_config": [
                {
                    "name": "namespace1/auth",
                    "targets_config": [
                        {"name": "namespace1/target1"},
                        {"name": "namespace1/target2"},
                    ],
                },
                {
                    "name": "namespace2/auth",
                    "targets_config": [
                        {"name": "namespace2/target1"},
                        {"name": "namespace2/target2"},
                    ],
                },
                # Add additional dependencies as needed
            ],
        },
    ],
    indirect=True,
)
def test_clone_with_invalid_root_repo(
    library_with_dependencies, origin_dir, client_dir
):
    # Invalidate the root repository
    root_repo = library_with_dependencies["root/auth"]["auth_repo"]
    setup_manager = SetupManager(root_repo)
    setup_manager = SetupManager(root_repo)
    setup_manager.add_task(update_timestamp_metadata_invalid_signature)
    setup_manager.execute_tasks()

    with pytest.raises(UpdateFailedError, match=INVALID_TIMESTAMP_PATTERN_ROOT):
        clone_full_library(
            library_with_dependencies,
            origin_dir,
            client_dir,
            expected_repo_type=UpdateType.EITHER,
            excluded_target_globs=None,
        )
