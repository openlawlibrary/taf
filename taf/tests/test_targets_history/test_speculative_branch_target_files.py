"""Comparing speculative branch commits with target files in both formats."""

from types import SimpleNamespace

import pytest

from taf.exceptions import InvalidBranchError
from taf.tests.test_targets_history.conftest import (
    PUBLICATION,
    TARGET_NAME,
    make_entry,
    make_history,
)
from taf.validation import _compare_commit_with_targets_metadata

SINGLE_OBJECT = make_entry("current")
HISTORY = make_history(2) + [make_entry("current", PUBLICATION)]


def _auth_repo_with_target_file(content):
    return SimpleNamespace(get_json=lambda _commit, _path: content)


@pytest.mark.parametrize(
    "content", [SINGLE_OBJECT, HISTORY], ids=["single-object", "list"]
)
def test_compare_commit_with_current_commit_of_target_file(content):
    _compare_commit_with_targets_metadata(
        _auth_repo_with_target_file(content),
        "auth-commit",
        SimpleNamespace(name=TARGET_NAME),
        make_entry("current")["commit"],
    )


@pytest.mark.parametrize(
    "content", [SINGLE_OBJECT, HISTORY], ids=["single-object", "list"]
)
def test_compare_commit_with_earlier_commit_of_target_file(content):
    earlier_commit = HISTORY[0]["commit"]

    with pytest.raises(InvalidBranchError, match="does not match"):
        _compare_commit_with_targets_metadata(
            _auth_repo_with_target_file(content),
            "auth-commit",
            SimpleNamespace(name=TARGET_NAME),
            earlier_commit,
        )
