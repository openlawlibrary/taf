import pytest
from taf.exceptions import UpdateFailedError
from taf.tests.test_updater.conftest import (
    SetupManager,
    update_role_metadata_invalid_signature,
)
from taf.updater.types.update import OperationType, UpdateType
from taf.tests.test_updater.update_utils import (
    _clone_full_library,
    invalidate_target_repo,
    update_and_check_commit_shas,
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
def test_update_repository_with_dependencies(
    library_with_dependencies,
    origin_dir,
    client_dir,
):
    _clone_full_library(
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

    with pytest.raises(UpdateFailedError, match=".*"):
        _clone_full_library(
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
    invalidate_target_repo(
        library_with_dependencies, "namespace1/auth", "namespace1/target1"
    )

    with pytest.raises(UpdateFailedError, match=".*"):
        _clone_full_library(
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
    invalidate_target_repo(
        library_with_dependencies, "namespace1/auth", "namespace1/target1"
    )

    # Try to update the library and expect an UpdateFailedError for the invalid repository
    with pytest.raises(UpdateFailedError, match=".*"):
        _clone_full_library(
            library_with_dependencies,
            origin_dir,
            client_dir,
            expected_repo_type=UpdateType.EITHER,
            excluded_target_globs=None,
        )

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
                except UpdateFailedError as e:
                    print(f"Failed to update repository {target_repo.name}: {e}")
