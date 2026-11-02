# test_update_library.py
import json

import pytest
from taf.exceptions import UpdateFailedError
from taf.tests.test_updater.conftest import (
    INVALID_TIMESTAMP_PATTERN,
    INVALID_TIMESTAMP_PATTERN_ROOT,
    KEYSTORE_PATH,
    TARGET_MISMATCH_PATTERN_DEPENDENCIES,
    SetupManager,
    add_unauthenticated_commits_to_all_target_repos,
    add_valid_target_commits,
    sign_target_files,
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
        )


@pytest.mark.parametrize(
    "library_with_dependencies",
    [
        {
            "dependencies_config": [
                {"name": "namespace1/auth"},
                {"name": "namespace2/auth"},
            ],
        },
    ],
    indirect=True,
)
def test_clone_with_dependency_without_out_of_band_commit(
    library_with_dependencies, origin_dir, client_dir, pin_manager
):
    root_auth_repo = library_with_dependencies["root/auth"]["auth_repo"]
    dependencies_path = root_auth_repo.path / "targets" / "dependencies.json"
    dependencies = json.loads(dependencies_path.read_text())
    del dependencies["dependencies"]["namespace1/auth"]["out-of-band-authentication"]
    dependencies_path.write_text(json.dumps(dependencies, indent=4))
    sign_target_files(
        origin_dir, root_auth_repo.name, keystore=KEYSTORE_PATH, pin_manager=pin_manager
    )

    with pytest.raises(
        UpdateFailedError,
        match="Dependency namespace1/auth has no out-of-band authentication commit",
    ):
        clone_full_library(
            library_with_dependencies,
            origin_dir,
            client_dir,
            expected_repo_type=UpdateType.EITHER,
        )
    assert not (client_dir / "namespace1" / "auth").exists()


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
        )
