import pytest
from taf.updater.types.update import UpdateType
from taf.tests.test_updater.update_utils import (
    clone_repositories,
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
def test_clone_repository_with_dependencies(
    library_with_dependencies,
    client_dir,
):
    clone_repositories(
        library_with_dependencies["root/auth"]["auth_repo"],
        client_dir,
        expected_repo_type=UpdateType.EITHER,
        excluded_target_globs=None,
    )
