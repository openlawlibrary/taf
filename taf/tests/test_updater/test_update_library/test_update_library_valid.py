import pytest
from taf.tests.test_updater.conftest import SetupManager, add_valid_target_commits
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
    clone_full_library(
        library_with_dependencies,
        origin_dir,
        client_dir,
        expected_repo_type=UpdateType.EITHER,
        excluded_target_globs=None,
    )
    auth_repo = library_with_dependencies["namespace1/auth"]["auth_repo"]
    setup_manager = SetupManager(auth_repo)
    setup_manager.add_task(add_valid_target_commits)
    setup_manager.execute_tasks()
    update_and_validate_repositories(library_with_dependencies, origin_dir, client_dir)
