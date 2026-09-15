"""
Target files of target repositories.

A target repository's target file (`targets/<namespace>/<name>`) records the commit
that the authentication repository authenticates for it. It comes in two formats:

- a single object describing only the current commit, e.g.
  `{"branch": "main", "commit": "<sha>", "build-date": "2026-01-15"}`
- a list of such objects, one per authenticated commit, oldest first. Entries are
  only ever appended, so the whole authenticated history is available at any commit
  of the authentication repository. The last entry is the current commit.

Both formats are read the same way: `get_tip` returns what the single object format
would contain. Besides `branch` and `commit`, an entry can hold `branch-id` and
`capstone`, which are used when validating speculative branches, and any other keys
(e.g. dates), which are treated as custom data.
"""

import json
from typing import Any, Dict, List, Optional, Union

import attrs

from taf.exceptions import InvalidTargetFileError, TargetsHistoryRewrittenError

BRANCH_KEY = "branch"
COMMIT_KEY = "commit"
BRANCH_ID_KEY = "branch-id"
CAPSTONE_KEY = "capstone"
NOT_CUSTOM_KEYS = (BRANCH_KEY, COMMIT_KEY, BRANCH_ID_KEY, CAPSTONE_KEY)

TargetFileContent = Union[Dict[str, Any], List[Dict[str, Any]]]


@attrs.frozen
class TargetEntry:
    """One authenticated commit of a target repository."""

    commit: str
    branch: Optional[str] = None
    branch_id: Optional[str] = None
    capstone: bool = False
    custom: Dict[str, Any] = attrs.Factory(dict)

    @classmethod
    def from_json(cls, data: Any, target_name: str = "") -> "TargetEntry":
        if not isinstance(data, dict) or not isinstance(data.get(COMMIT_KEY), str):
            raise InvalidTargetFileError(
                target_name, f"expected an object with a commit, got {data!r}"
            )
        return cls(  # type: ignore[call-arg]
            commit=data[COMMIT_KEY],
            branch=data.get(BRANCH_KEY),
            branch_id=data.get(BRANCH_ID_KEY),
            capstone=data.get(CAPSTONE_KEY, False),
            custom={
                key: value for key, value in data.items() if key not in NOT_CUSTOM_KEYS
            },
        )


def is_history(content: Any) -> bool:
    """Whether target file content is in the list format."""
    return isinstance(content, list)


def parse_target_file(content: Any, target_name: str = "") -> List[TargetEntry]:
    """
    Entries of a target file, oldest first. A target file in the single object format
    has one entry.

    Raises:
        InvalidTargetFileError: if the content is not a valid target file.
    """
    if isinstance(content, dict):
        return [TargetEntry.from_json(content, target_name)]
    if is_history(content):
        if not content:
            raise InvalidTargetFileError(target_name, "the list of commits is empty")
        return [TargetEntry.from_json(entry, target_name) for entry in content]
    raise InvalidTargetFileError(
        target_name, f"expected an object or a list, got {type(content).__name__}"
    )


def get_tip(content: Any, target_name: str = "") -> Dict[str, Any]:
    """
    The current commit of a target file in the single object format, i.e. the target
    file itself or the last entry of the list.

    Raises:
        InvalidTargetFileError: if the content is not a valid target file.
    """
    parse_target_file(content, target_name)
    tip = content[-1] if is_history(content) else content
    return dict(tip)


def check_append(
    previous: Optional[Any], current: Optional[Any], target_name: str = ""
) -> None:
    """
    Check that a target file changed in a way allowed between two consecutive commits
    of the authentication repository. `previous` and `current` are the parsed
    contents at those commits, None if the file did not exist.

    A list may only grow by one entry at the end, and existing entries may not change.
    A list cannot be replaced by a single object, and an existing single object cannot
    be replaced by a list. A new target file may be a list with one entry. Single
    object target files may change freely, and any target file may be removed.

    Raises:
        InvalidTargetFileError: if either content is not a valid target file.
        TargetsHistoryRewrittenError: if the change is not allowed.
    """
    if previous is not None:
        parse_target_file(previous, target_name)
    if current is None:
        return
    parse_target_file(current, target_name)

    if not is_history(current):
        if is_history(previous):
            raise TargetsHistoryRewrittenError(
                target_name, "the list of commits was replaced by a single commit"
            )
        return

    if previous is None:
        if len(current) > 1:
            raise TargetsHistoryRewrittenError(
                target_name,
                f"a new target file can list one commit, but lists {len(current)}",
            )
        return
    if not is_history(previous):
        raise TargetsHistoryRewrittenError(
            target_name, "a single commit was replaced by a list of commits"
        )
    if len(current) < len(previous):
        raise TargetsHistoryRewrittenError(
            target_name,
            f"{len(previous) - len(current)} commit(s) were removed from the list",
        )
    if current[: len(previous)] != previous:
        raise TargetsHistoryRewrittenError(
            target_name, "previously listed commits were modified"
        )
    if len(current) - len(previous) > 1:
        raise TargetsHistoryRewrittenError(
            target_name,
            f"{len(current) - len(previous)} commits were added, but at most one "
            "can be added at a time",
        )


def serialize_target_file(content: TargetFileContent) -> str:
    """
    Target file content as written to disk. A list is written one entry per line, so
    that appending an entry adds one line.
    """
    if not is_history(content):
        return json.dumps(content, indent=4)
    return (
        "[\n"
        + ",\n".join(json.dumps(entry, separators=(",", ":")) for entry in content)
        + "\n]"
    )
