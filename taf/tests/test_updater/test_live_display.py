import os
import sys

import pytest

from taf.log import (
    _add_console_logger,
    console_loggers,
    disable_console_logging,
    taf_logger,
)
from taf.tests.test_updater.conftest import (
    TARGET_COMMIT_AFTER_LAST_VALIDATED_PATTERN,
    SetupManager,
    add_unauthenticated_commits_to_all_target_repos,
)
from taf.tests.test_updater.update_utils import (
    clone_repositories,
    update_invalid_repos_and_check_if_repos_exist,
)
from taf.updater import live_display
from taf.updater.live_display import RowState
from taf.updater.types.update import OperationType


@pytest.fixture
def console_logging():
    disable_console_logging()
    _add_console_logger(sys.stdout)
    yield
    disable_console_logging()


def test_console_logging_writes_to_stdout_again_after_display(console_logging):
    # rich only swaps sys.stdout while the display runs if it writes to a terminal
    previous = os.environ.get("TTY_COMPATIBLE")
    os.environ["TTY_COMPATIBLE"] = "1"
    try:
        with live_display.show():
            pass
    finally:
        if previous is None:
            del os.environ["TTY_COMPATIBLE"]
        else:
            os.environ["TTY_COMPATIBLE"] = previous

    # loguru keeps the stream a handler writes to on its private handler object
    handler = taf_logger._core.handlers[console_loggers["log"]]
    assert handler._sink._stream is sys.stdout


@pytest.mark.parametrize(
    "origin_auth_repo",
    [{"targets_config": [{"name": "target1"}, {"name": "target2"}]}],
    indirect=True,
)
def test_clone_shows_completed_row(origin_auth_repo, client_dir):
    with live_display.show() as display:
        clone_repositories(origin_auth_repo, client_dir)

    assert [(row.label, row.state) for row in display.rows] == [
        (origin_auth_repo.name, RowState.COMPLETE)
    ]


@pytest.mark.parametrize(
    "origin_auth_repo",
    [{"targets_config": [{"name": "target1"}, {"name": "target2"}]}],
    indirect=True,
)
def test_failed_clone_shows_error_row(origin_auth_repo, client_dir):
    setup_manager = SetupManager(origin_auth_repo)
    setup_manager.add_task(add_unauthenticated_commits_to_all_target_repos)
    setup_manager.execute_tasks()

    with live_display.show() as display:
        update_invalid_repos_and_check_if_repos_exist(
            OperationType.CLONE,
            origin_auth_repo,
            client_dir,
            TARGET_COMMIT_AFTER_LAST_VALIDATED_PATTERN,
            True,
        )

    assert [(row.label, row.state) for row in display.rows] == [
        (origin_auth_repo.name, RowState.ERROR)
    ]
