"""Live, in-place display of the updater's progress in the terminal.

Each authentication repository the updater works on (the root repository and
its dependencies) gets a row with its state, current step and elapsed time.
Rows are only shown while `show` is active, which the CLI enables when writing
to a terminal - when the updater is used as a library nothing is displayed.
"""

import threading
import time
from contextlib import contextmanager
from enum import Enum
from typing import Callable, List, Optional

from rich.console import Console, Group, RenderableType
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

import taf.settings as settings
from taf.log import console_logging_to

MAX_MESSAGE_LINES = 8


class RowState(Enum):
    WAITING = "waiting"
    RUNNING = "running"
    ERROR = "error"
    COMPLETE = "complete"


_STATE_STYLES = {
    RowState.WAITING: "dim",
    RowState.RUNNING: "yellow",
    RowState.ERROR: "red",
    RowState.COMPLETE: "green",
}


# what a running repository is shown as doing, for the pipeline steps that take
# noticeable time; quicker steps keep showing the previous activity
_STEP_ACTIVITIES = {
    "clone_auth_to_temp": "cloning",
    "clone_or_fetch_users_auth_repo": "fetching",
    "clone_target_repositories_to_temp": "cloning",
    "get_target_repositories_commits": "fetching",
    "run_tuf_updater": "validating",
    "validate_last_validated_commit": "validating",
    "validate_target_repositories": "validating",
    "validate_and_set_additional_commits_of_target_repositories": "validating",
    "update_users_target_repositories": "merging",
    "merge_commits": "merging",
    "merge_auth_commits": "merging",
}


class Row:
    def __init__(self, label: Callable[[], str]):
        self._label = label
        self.state = RowState.WAITING
        self.step: Optional[str] = None
        self.activity: Optional[str] = None
        self.start_time: Optional[float] = None
        self.end_time: Optional[float] = None

    @property
    def label(self) -> str:
        return self._label()

    def start(self):
        self.state = RowState.RUNNING
        self.start_time = time.monotonic()

    def set_step(self, step_name: str):
        self.step = step_name.replace("_", " ")
        self.activity = _STEP_ACTIVITIES.get(step_name, self.activity)

    @property
    def status(self) -> str:
        if self.state == RowState.RUNNING and self.activity:
            return self.activity
        return self.state.value

    def finish(self, failed: bool):
        self.state = RowState.ERROR if failed else RowState.COMPLETE
        self.end_time = time.monotonic()

    @property
    def elapsed(self) -> Optional[float]:
        if self.start_time is None:
            return None
        end = self.end_time if self.end_time is not None else time.monotonic()
        return end - self.start_time


class LiveDisplay:
    def __init__(self):
        self._rows: List[Row] = []
        self._messages: List[Text] = []
        self._lock = threading.Lock()

    def add_message(self, message) -> None:
        lines = [
            line
            for line in Text.from_ansi(str(message)).split("\n")
            if line.plain.strip()
        ]
        if not lines:
            return
        with self._lock:
            self._messages.append(Text("\n").join(lines))

    @property
    def messages(self) -> List[Text]:
        with self._lock:
            return list(self._messages)

    def _recent_message_lines(self) -> List[Text]:
        with self._lock:
            recent: List[Text] = []
            for message in reversed(self._messages):
                recent[:0] = message.split("\n")
                if len(recent) >= MAX_MESSAGE_LINES:
                    break
        lines = recent[-MAX_MESSAGE_LINES:]
        for line in lines:
            line.no_wrap = True
            line.overflow = "ellipsis"
        return lines

    def add_row(self, row: Row):
        with self._lock:
            self._rows.append(row)

    @property
    def rows(self) -> List[Row]:
        with self._lock:
            return list(self._rows)

    def _table(self) -> Table:
        show_steps = settings.VERBOSITY >= 1
        table = Table(box=None, padding=(0, 2), show_edge=False)
        table.add_column("Repository")
        table.add_column("Status")
        if show_steps:
            table.add_column("Step")
        table.add_column("Time", justify="right")
        for row in self.rows:
            elapsed = row.elapsed
            cells = [
                row.label,
                Text(row.status, style=_STATE_STYLES[row.state]),
            ]
            if show_steps:
                cells.append(row.step if row.state == RowState.RUNNING else "")
            cells.append(f"{elapsed:.1f}s" if elapsed is not None else "")
            table.add_row(*cells)
        return table

    def __rich__(self) -> RenderableType:
        table = self._table()
        lines = self._recent_message_lines()
        if not lines:
            return table
        return Group(table, Panel(Group(*lines), title="Log", border_style="dim"))


_active: Optional[LiveDisplay] = None


def add_row(label: Callable[[], str]) -> Row:
    """Create a row for a unit of work. It is displayed only if a live display is
    active; otherwise updating it has no visible effect."""
    row = Row(label)
    if _active is not None:
        _active.add_row(row)
    return row


@contextmanager
def show(enabled: bool = True):
    """Show the live display for the duration of the block. Log output is collected
    in a panel under the table while the block runs. When the block ends the display
    is cleared and the log output is printed in full, as it would be without it."""
    global _active
    if not enabled:
        yield None
        return

    display = LiveDisplay()
    console = Console()
    _active = display
    try:
        # entered before Live, so the logger is restored after Live has put
        # back the real stdout it replaces while running
        with console_logging_to(display.add_message):
            try:
                with Live(
                    display, console=console, refresh_per_second=4, transient=True
                ):
                    yield display
            finally:
                for message in display.messages:
                    console.print(message)
    finally:
        _active = None
