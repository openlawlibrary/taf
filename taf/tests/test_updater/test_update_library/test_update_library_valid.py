import pytest
from taf.tests.test_updater.conftest import SetupManager

# , add_valid_target_commits
from taf.updater.types.update import UpdateType
from taf.tests.test_updater.update_utils import (
    _clone_full_library,
    update_and_validate_repositories,
)
from ..conftest import remove_last_validate_commit


# @pytest.mark.parametrize(
#     "library_with_dependencies",
#     [
#         {
#             "targets_config": [{"name": "target1"}, {"name": "target2"}],
#             "dependencies_config": [
#                 {
#                     "name": "namespace1/auth",
#                     "targets_config": [
#                         {"name": "namespace1/target1"},
#                         {"name": "namespace1/target2"},
#                     ],
#                 },
#                 {
#                     "name": "namespace2/auth",
#                     "targets_config": [
#                         {"name": "namespace2/target1"},
#                         {"name": "namespace2/target2"},
#                     ],
#                 },
#                 # Add additional dependencies as needed
#             ],
#         },
#     ],
#     indirect=True,
# )
# def test_update_repository_with_dependencies(
#     library_with_dependencies,
#     origin_dir,
#     client_dir,
# ):
#     _clone_full_library(
#         library_with_dependencies,
#         origin_dir,
#         client_dir,
#         expected_repo_type=UpdateType.EITHER,
#         excluded_target_globs=None,
#     )
#     auth_repo = library_with_dependencies["namespace1/auth"]["auth_repo"]
#     setup_manager = SetupManager(auth_repo)
#     setup_manager.add_task(add_valid_target_commits)
#     setup_manager.execute_tasks()
#     update_and_validate_repositories(library_with_dependencies, origin_dir, client_dir)


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
def test_update_repository_with_dependencies_where_top_level_last_valid_commit_is_deleted_expect_update_successful(
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
    auth_repo = library_with_dependencies["namespace1/auth"]["auth_repo"]
    root_repo = library_with_dependencies["root/auth"]["auth_repo"]
    remove_last_validate_commit(client_dir, root_repo.name)
    setup_manager = SetupManager(auth_repo)
    # setup_manager.add_task(add_valid_target_commits)
    setup_manager.execute_tasks()
    update_and_validate_repositories(library_with_dependencies, origin_dir, client_dir)
