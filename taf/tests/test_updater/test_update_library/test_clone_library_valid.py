import pytest
from taf.tests.test_updater.conftest import SetupManager
from taf.tests.test_updater.test_update_library.conftest import set_dependency
from taf.updater import live_display
from taf.updater.live_display import RowState
from taf.updater.types.update import UpdateType
from taf.tests.test_updater.update_utils import (
    clone_full_library,
)

DEPENDENCIES_CONFIG = [
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
]


@pytest.mark.parametrize(
    "library_with_dependencies",
    [
        {
            "targets_config": [{"name": "target1"}, {"name": "target2"}],
            "dependencies_config": DEPENDENCIES_CONFIG,
        },
    ],
    indirect=True,
)
def test_clone_repository_with_dependencies(
    library_with_dependencies,
    origin_dir,
    client_dir,
):
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
            "dependencies_config": DEPENDENCIES_CONFIG,
        },
    ],
    indirect=True,
)
def test_clone_repository_with_dependencies_when_one_name_is_invalid(
    library_with_dependencies, origin_dir, client_dir
):
    setup_manager = SetupManager(library_with_dependencies["root/auth"]["auth_repo"])
    setup_manager.add_task(
        set_dependency,
        kwargs={"dependency_name": "namespace3-auth", "dependency_data": {}},
    )
    setup_manager.execute_tasks()

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
            "dependencies_config": DEPENDENCIES_CONFIG,
        },
    ],
    indirect=True,
)
def test_clone_repository_with_dependencies_shows_a_row_per_repository(
    library_with_dependencies,
    origin_dir,
    client_dir,
):
    with live_display.show() as display:
        clone_full_library(library_with_dependencies, origin_dir, client_dir)

    rows = {row.label: row for row in display.rows}
    assert set(rows) == {"root/auth", "namespace1/auth", "namespace2/auth"}
    for row in rows.values():
        assert row.state == RowState.COMPLETE
        assert row.elapsed is not None
