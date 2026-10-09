import sys

import pytest
from rich.console import Console

import taf.settings as settings
from taf.log import _add_console_logger, console_loggers, taf_logger
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
from taf.updater.live_display import LiveDisplay, RowState
from taf.updater.types.update import OperationType


@pytest.fixture
def console_logging():
    had_console_logger = "log" in console_loggers
    if not had_console_logger:
        _add_console_logger(sys.stdout)
    yield
    if not had_console_logger:
        taf_logger.remove(console_loggers.pop("log"))


def render(display):
    console = Console(width=80)
    with console.capture() as capture:
        console.print(display)
    return capture.get()


def test_rows_are_shown_only_while_display_is_active():
    outside = live_display.add_row(lambda: "outside")
    with live_display.show() as display:
        inside = live_display.add_row(lambda: "inside")
    assert display.rows == [inside]
    assert outside not in display.rows


def test_row_tracks_state_step_and_elapsed_time():
    row = live_display.Row(lambda: "ns/auth")
    assert row.state == RowState.WAITING
    assert row.elapsed is None

    row.start()
    row.set_step("validate_target_repositories")
    assert row.state == RowState.RUNNING
    assert row.step == "validate target repositories"

    row.finish(failed=True)
    assert row.state == RowState.ERROR
    elapsed = row.elapsed
    assert elapsed is not None
    assert row.elapsed == elapsed


def test_messages_drop_the_blank_lines_around_them():
    display = LiveDisplay()
    display.add_message("\n\x1b[37m\nUpdate started\n\x1b[0m")
    display.add_message("\n\n")

    assert [message.plain for message in display.messages] == ["Update started"]


def test_message_panel_shows_only_the_latest_lines():
    display = LiveDisplay()
    for i in range(12):
        display.add_message(f"message {i}")

    output = render(display)

    assert "Log" in output
    assert "message 11" in output and "message 4" in output
    assert "message 3" not in output


def test_no_message_panel_without_messages_or_once_hidden():
    display = LiveDisplay()
    assert "Log" not in render(display)

    display.add_message("a message")
    assert "a message" in render(display)

    display.show_messages = False
    assert "a message" not in render(display)


def test_console_logging_writes_to_stdout_again_after_display(console_logging):
    with live_display.show():
        pass

    # loguru keeps the stream a handler writes to on its private handler object
    handler = taf_logger._core.handlers[console_loggers["log"]]
    assert handler._sink._stream is sys.stdout


def test_messages_are_printed_above_the_final_table(console_logging, capsys):
    with live_display.show() as display:
        live_display.add_row(lambda: "ns/auth").start()
        taf_logger.log("NOTICE", "first message")
        taf_logger.warning("second message")

    output = capsys.readouterr().out
    assert [message.plain for message in display.messages] == [
        "first message",
        "second message",
    ]
    assert (
        output.index("first message")
        < output.index("second message")
        < output.rindex("Repository")
    )


@pytest.mark.parametrize("verbosity, step_column", [(0, False), (1, True), (2, True)])
def test_step_column_is_shown_from_verbosity_one(verbosity, step_column):
    display = LiveDisplay()
    display.add_row(live_display.Row(lambda: "ns/auth"))

    original_verbosity = settings.VERBOSITY
    settings.VERBOSITY = verbosity
    try:
        columns = [column.header for column in display.__rich__().columns]
    finally:
        settings.VERBOSITY = original_verbosity

    assert columns == ["Repository", "Status"] + (["Step"] if step_column else []) + [
        "Time"
    ]


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
