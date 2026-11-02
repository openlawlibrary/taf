import json

import pytest
from taf.tests.test_updater.conftest import KEYSTORE_PATH, sign_target_files
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
    library_with_dependencies, origin_dir, client_dir, pin_manager
):
    root_auth_repo = library_with_dependencies["root/auth"]["auth_repo"]
    dependencies_path = root_auth_repo.path / "targets" / "dependencies.json"
    dependencies = json.loads(dependencies_path.read_text())
    dependencies["dependencies"]["namespace3-auth"] = {}
    dependencies_path.write_text(json.dumps(dependencies, indent=4))
    sign_target_files(
        origin_dir, root_auth_repo.name, keystore=KEYSTORE_PATH, pin_manager=pin_manager
    )

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
