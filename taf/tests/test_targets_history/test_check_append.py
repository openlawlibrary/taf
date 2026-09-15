"""How a target file may change between consecutive authentication repository commits."""

import pytest

from taf.exceptions import (
    InvalidTargetFileError,
    TargetsHistoryRewrittenError,
    UpdateFailedError,
)
from taf.targets_history import check_append
from taf.tests.test_targets_history.conftest import (
    PUBLICATION,
    TARGET_NAME,
    make_entry,
    make_history,
)

HISTORY = make_history(3)


def _with_changed_entry(history, index, **changes):
    changed = [dict(entry) for entry in history]
    changed[index].update(changes)
    return changed


@pytest.mark.parametrize(
    "previous, current",
    [
        (None, None),
        (None, make_entry()),
        (make_entry("old"), make_entry("new")),
        (make_entry(), None),
        (None, make_history(1)),
        (HISTORY, HISTORY),
        (HISTORY, HISTORY + [make_entry("appended")]),
        (HISTORY, HISTORY + [make_entry("new-branch", PUBLICATION)]),
        (HISTORY, None),
    ],
    ids=[
        "no-target-file",
        "new-single-object",
        "single-object-changed",
        "single-object-removed",
        "new-list-with-one-commit",
        "list-unchanged",
        "list-commit-appended",
        "list-commit-on-new-branch-appended",
        "list-removed",
    ],
)
def test_check_append_allows(previous, current):
    check_append(previous, current, TARGET_NAME)


@pytest.mark.parametrize(
    "previous, current, reason",
    [
        (HISTORY, make_entry(), "replaced by a single commit"),
        (make_entry(), make_history(1), "single commit was replaced by a list"),
        (None, make_history(2), "a new target file can list one commit"),
        (HISTORY, HISTORY[:-1], "1 commit\\(s\\) were removed"),
        (
            HISTORY,
            _with_changed_entry(HISTORY, 0, commit=make_entry("forged")["commit"]),
            "previously listed commits were modified",
        ),
        (
            HISTORY,
            _with_changed_entry(HISTORY, 1, **{"build-date": "2020-01-01"}),
            "previously listed commits were modified",
        ),
        (
            HISTORY,
            _with_changed_entry(HISTORY, 2, commit=make_entry("replaced")["commit"]),
            "previously listed commits were modified",
        ),
        (
            HISTORY,
            [HISTORY[1], HISTORY[0], HISTORY[2]],
            "previously listed commits were modified",
        ),
        (
            HISTORY,
            HISTORY + [make_entry("first"), make_entry("second")],
            "2 commits were added, but at most one can be added at a time",
        ),
    ],
    ids=[
        "list-replaced-by-single-object",
        "single-object-replaced-by-list",
        "new-list-with-more-than-one-commit",
        "commit-removed",
        "old-commit-changed",
        "old-commit-custom-data-changed",
        "last-commit-changed",
        "commits-reordered",
        "more-than-one-commit-appended",
    ],
)
def test_check_append_rejects(previous, current, reason):
    with pytest.raises(TargetsHistoryRewrittenError, match=reason) as error:
        check_append(previous, current, TARGET_NAME)

    assert error.value.target_name == TARGET_NAME
    assert str(error.value).startswith(f"Target file {TARGET_NAME} was rewritten: ")


def test_rewritten_target_file_is_update_failure():
    with pytest.raises(UpdateFailedError):
        check_append(HISTORY, HISTORY[:-1], TARGET_NAME)


@pytest.mark.parametrize(
    "previous, current",
    [([], HISTORY), (HISTORY, []), ("a3f1c2", make_entry()), (make_entry(), 42)],
    ids=[
        "previous-empty-list",
        "current-empty-list",
        "previous-string",
        "current-number",
    ],
)
def test_check_append_rejects_invalid_target_file(previous, current):
    with pytest.raises(InvalidTargetFileError, match=TARGET_NAME):
        check_append(previous, current, TARGET_NAME)
