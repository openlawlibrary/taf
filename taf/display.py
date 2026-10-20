"""What is shared by everything that shows the state of repositories in the
terminal - the styles, the wording of common states and the way a repository
is printed together with its properties - so that the same thing looks the
same in the updater's live display and in the commands which print the state
of repositories.
"""

from typing import Any, Dict, List, Optional, Tuple

from rich.console import Console
from rich.text import Text

STYLE_OK = "green"
STYLE_ATTENTION = "yellow"
STYLE_ERROR = "red"
STYLE_INACTIVE = "dim"

INDENT = "  "

# wide enough for lines not to be folded when the output is not a terminal,
# whose width rich would otherwise assume to be 80
WIDTH_WHEN_NOT_A_TERMINAL = 1000


def default_console() -> Console:
    console = Console()
    if not console.is_terminal:
        console = Console(width=WIDTH_WHEN_NOT_A_TERMINAL)
    return console


def yes_no(value: Optional[bool], ok_when: Optional[bool] = None) -> Text:
    """Text of a yes/no state. If it is known which of the two values is the
    expected one, the other one is highlighted."""
    text = "yes" if value else "no"
    if ok_when is None:
        return Text(text)
    return Text(text, style=STYLE_OK if value == ok_when else STYLE_ATTENTION)


def up_to_date(status: Dict[str, Any]) -> Text:
    if not status.get("has-remote", True):
        return Text("no remote", style=STYLE_INACTIVE)
    return yes_no(status.get("up-to-date"), ok_when=True)


def print_properties(
    console: Console,
    label: str,
    name: str,
    properties: List[Tuple[str, Text]],
    depth: int = 0,
) -> None:
    """Print what something is and its name, followed by its properties, one
    per line:

    Target repository: namespace/target1
      Cloned: yes
      Bare: no
    """
    console.print(Text.assemble(INDENT * depth, f"{label}: ", (name, "bold")))
    for property_label, value in properties:
        console.print(Text.assemble(INDENT * (depth + 1), f"{property_label}: ", value))
