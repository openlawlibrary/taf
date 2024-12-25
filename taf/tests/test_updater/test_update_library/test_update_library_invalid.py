# test_update_library.py
import pytest
from taf.exceptions import UpdateFailedError
from taf.tests.test_updater.conftest import (
    INVALID_TIMESTAMP_PATTERN,
    TARGET_MISMATCH_PATTERN_DEPENDENCIES,
    SetupManager,
    add_unauthenticated_commits_to_all_target_repos,
    add_valid_target_commits,
    update_timestamp_metadata_invalid_signature,
)
from taf.updater.types.update import UpdateType
from taf.tests.test_updater.update_utils import (
    clone_full_library,
    update_and_validate_repositories,
)


@pytest.mark.parametrize(
    "library_with_dependencies",
    [
        {
            "targets_config": [{"name": "target1"}, {"name": "target2"}],
            "dependencies_config": [
                {
                    "name": "namespace11/auth",
                    "targets_config": [
                        {"name": "namespace11/target1"},
                        {"name": "namespace11/target2"},
                    ],
                },
                {
                    "name": "namespace12/auth",
                    "targets_config": [
                        {"name": "namespace12/target1"},
                        {"name": "namespace12/target2"},
                    ],
                },
                # Add additional dependencies as needed
            ],
        },
    ],
    indirect=True,
)
def test_update_with_invalid_dependency_repo(
    library_with_dependencies, origin_dir, client_dir
):

    clone_full_library(
        library_with_dependencies,
        origin_dir,
        client_dir,
        expected_repo_type=UpdateType.EITHER,
        excluded_target_globs=None,
    )
    # Invalidate one of the authentication repositories in dependencies
    dependency_auth_repo = library_with_dependencies["namespace11/auth"]["auth_repo"]
    setup_manager = SetupManager(dependency_auth_repo)
    setup_manager.add_task(update_timestamp_metadata_invalid_signature)
    setup_manager.execute_tasks()

    with pytest.raises(UpdateFailedError, match=INVALID_TIMESTAMP_PATTERN):
        update_and_validate_repositories(
            library_with_dependencies, origin_dir, client_dir
        )


@pytest.mark.parametrize(
    "library_with_dependencies",
    [
        {
            "targets_config": [{"name": "target1"}, {"name": "target2"}],
            "dependencies_config": [
                {
                    "name": "namespace21/auth",
                    "targets_config": [
                        {"name": "namespace21/target1"},
                        {"name": "namespace21/target2"},
                    ],
                },
                {
                    "name": "namespace22/auth",
                    "targets_config": [
                        {"name": "namespace22/target1"},
                        {"name": "namespace22/target2"},
                    ],
                },
                # Add additional dependencies as needed
            ],
        },
    ],
    indirect=True,
)
def test_update_invalid_target_repo(
    library_with_dependencies,
    origin_dir,
    client_dir,
):
    clone_full_library(
        library_with_dependencies,
        origin_dir,
        client_dir,
        expected_repo_type=UpdateType.EITHER,
        excluded_target_globs=None,
    )
    # Invalidate one of the target repositories
    dependency_auth_repo = library_with_dependencies["namespace21/auth"]["auth_repo"]
    setup_manager = SetupManager(dependency_auth_repo)
    setup_manager.add_task(add_valid_target_commits)
    setup_manager.add_task(add_unauthenticated_commits_to_all_target_repos)
    setup_manager.add_task(add_valid_target_commits)
    setup_manager.execute_tasks()

    with pytest.raises(UpdateFailedError, match=TARGET_MISMATCH_PATTERN_DEPENDENCIES):
        update_and_validate_repositories(
            library_with_dependencies, origin_dir, client_dir
        )


@pytest.mark.parametrize(
    "library_with_dependencies",
    [
        {
            "targets_config": [{"name": "target1"}, {"name": "target2"}],
            "dependencies_config": [
                {
                    "name": "namespace31/auth",
                    "targets_config": [
                        {"name": "namespace31/target1"},
                        {"name": "namespace31/target2"},
                    ],
                },
                {
                    "name": "namespace32/auth",
                    "targets_config": [
                        {"name": "namespace32/target1"},
                        {"name": "namespace32/target2"},
                    ],
                },
                # Add additional dependencies as needed
            ],
        },
    ],
    indirect=True,
)
def test_update_all_except_invalid(
    library_with_dependencies,
    origin_dir,
    client_dir,
):

    clone_full_library(
        library_with_dependencies,
        origin_dir,
        client_dir,
        expected_repo_type=UpdateType.EITHER,
        excluded_target_globs=None,
    )
    # Invalidate one of the target repositories of a referenced authentication repository
    dependency_auth_repo = library_with_dependencies["namespace31/auth"]["auth_repo"]
    setup_manager = SetupManager(dependency_auth_repo)
    setup_manager.add_task(add_valid_target_commits)
    setup_manager.add_task(add_unauthenticated_commits_to_all_target_repos)
    setup_manager.add_task(add_valid_target_commits)
    setup_manager.execute_tasks()

    # Run the updater which will clone and then update
    with pytest.raises(UpdateFailedError, match=TARGET_MISMATCH_PATTERN_DEPENDENCIES):
        update_and_validate_repositories(
            library_with_dependencies, origin_dir, client_dir
        )

    # Push valid commits to another target repository
    setup_manager.add_task(add_valid_target_commits)
    setup_manager.execute_tasks()

    # Validate that the valid repositories were updated successfully, skipping the invalid ones
    update_and_validate_repositories(
        library_with_dependencies,
        origin_dir,
        client_dir,
        invalid_target_names=["namespace31/target1"],
    )
