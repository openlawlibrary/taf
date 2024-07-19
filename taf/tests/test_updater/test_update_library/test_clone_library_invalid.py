# test_update_library.py
import pytest
from taf.exceptions import UpdateFailedError
from taf.tests.test_updater.conftest import (
    CANNOT_CLONE_TARGET_PATTERN,
    INVALID_TIMESTAMP_PATTERN,
    SetupManager,
    update_role_metadata_invalid_signature,
)
from taf.updater.types.update import OperationType, UpdateType
from taf.tests.test_updater.update_utils import (
    invalidate_target_repo,
    update_and_check_commit_shas,
    check_if_commits_match,
    update_full_library,
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
def test_update_with_invalid_dependency_repo(
    library_with_dependencies, origin_dir, client_dir
):
    # Invalidate one of the authentication repositories in dependencies
    dependency_auth_repo = library_with_dependencies["namespace1/auth"]["auth_repo"]
    setup_manager = SetupManager(dependency_auth_repo)
    setup_manager.add_task(
        update_role_metadata_invalid_signature, kwargs={"role": "timestamp"}
    )
    setup_manager.execute_tasks()

    # Run the updater which will clone and then update
    with pytest.raises(UpdateFailedError, match=INVALID_TIMESTAMP_PATTERN):
        update_full_library(
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
def test_update_invalid_target_repo(
    library_with_dependencies,
    origin_dir,
    client_dir,
):
    # Invalidate one of the target repositories
    auth_repo = library_with_dependencies["namespace1/auth"]["auth_repo"]
    setup_manager = SetupManager(auth_repo)
    setup_manager.add_task(
        invalidate_target_repo,
        kwargs={
            "library_with_dependencies": library_with_dependencies,
            "namespace": "namespace1/auth",
            "target_name": "namespace1/target1",
        },
    )
    setup_manager.execute_tasks()

    # Run the updater which will clone and then update
    with pytest.raises(UpdateFailedError, match=CANNOT_CLONE_TARGET_PATTERN):
        update_full_library(
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
def test_update_all_except_invalid(
    library_with_dependencies,
    origin_dir,
    client_dir,
):
    # Invalidate one of the target repositories of a referenced authentication repository
    auth_repo = library_with_dependencies["namespace1/auth"]["auth_repo"]
    setup_manager = SetupManager(auth_repo)
    setup_manager.add_task(
        invalidate_target_repo,
        kwargs={
            "library_with_dependencies": library_with_dependencies,
            "namespace": "namespace1/auth",
            "target_name": "namespace1/target1",
        },
    )
    setup_manager.execute_tasks()

    # Run the updater which will clone and then update
    with pytest.raises(UpdateFailedError, match=CANNOT_CLONE_TARGET_PATTERN):
        update_full_library(
            library_with_dependencies,
            origin_dir,
            client_dir,
            expected_repo_type=UpdateType.EITHER,
            excluded_target_globs=None,
        )

    # Verify that the valid repositories were updated successfully
    for auth_repo_name, repo_info in library_with_dependencies.items():
        auth_repo = repo_info["auth_repo"]
        for target_repo in repo_info["target_repos"]:
            if target_repo.name != "namespace1/target1":
                try:
                    update_and_check_commit_shas(
                        OperationType.UPDATE,
                        auth_repo,
                        client_dir,
                    )
                    # Verify that the commit SHAs are the same
                    check_if_commits_match(
                        {auth_repo_name: auth_repo, target_repo.name: target_repo},
                        origin_dir,
                    )
                except UpdateFailedError as e:
                    print(f"Failed to update repository {target_repo.name}: {e}")
