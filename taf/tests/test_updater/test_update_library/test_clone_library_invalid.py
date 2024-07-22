# test_update_library.py
import pytest
from taf.exceptions import UpdateFailedError
from taf.tests.test_updater.conftest import (
    INVALID_TIMESTAMP_PATTERN,
    CANNOT_CLONE_TARGET_PATTERN,
    SetupManager,
    update_role_metadata_invalid_signature,
    invalidate_target_repo,
)
from taf.updater.types.update import OperationType, UpdateType
from taf.tests.test_updater.update_utils import (
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
def test_clone_with_invalid_dependency_repo(library_with_dependencies, client_dir):
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
            client_dir,
            operation=OperationType.CLONE,
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
            client_dir,
            operation=OperationType.CLONE,
            expected_repo_type=UpdateType.EITHER,
            excluded_target_globs=None,
        )
