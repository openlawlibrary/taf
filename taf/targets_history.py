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
from typing import Any, Dict, Iterable, List, Optional, Tuple, Union

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


def check_target_file_versions(
    target_name: str,
    versions: Iterable[Tuple[Any, Optional[str]]],
    previous: Optional[str] = None,
) -> None:
    """
    Check with `check_append` how a target file changed across consecutive commits of
    the authentication repository.

    Arguments:
        target_name: Name of the target file.
        versions: (authentication commit, raw content of the target file) pairs, oldest
            first. Content is None at commits where the target file does not exist.
        previous: Raw content of the target file at the commit before the first
            version, None if it did not exist.

    Only changes to or from a list are parsed, so checking target files that were never
    lists does not parse them.

    Raises:
        InvalidTargetFileError: if a version involved in such a change is not a valid
            target file.
        TargetsHistoryRewrittenError: if a change is not allowed.
    """
    previous_content = None
    previous_parsed = False
    for auth_commit, current in versions:
        if current != previous and (_is_list(previous) or _is_list(current)):
            try:
                if not previous_parsed:
                    previous_content = _load(previous, target_name)
                current_content = _load(current, target_name)
                check_append(previous_content, current_content, target_name)
            except TargetsHistoryRewrittenError as e:
                raise TargetsHistoryRewrittenError(
                    target_name, e.reason, auth_commit
                ) from e
            except InvalidTargetFileError as e:
                raise InvalidTargetFileError(target_name, e.reason, auth_commit) from e
            previous_content = current_content
            previous_parsed = True
        elif current != previous:
            previous_parsed = False
        previous = current


def _is_list(raw: Optional[str]) -> bool:
    return raw is not None and raw.lstrip().startswith("[")


def _load(raw: Optional[str], target_name: str) -> Any:
    if raw is None:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        raise InvalidTargetFileError(target_name, f"not valid JSON ({e})")


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
