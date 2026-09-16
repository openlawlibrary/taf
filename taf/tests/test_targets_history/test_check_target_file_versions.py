"""Checking how a target file changed across a sequence of authentication repository commits."""

import pytest

import taf.targets_history as targets_history
from taf.exceptions import InvalidTargetFileError, TargetsHistoryRewrittenError
from taf.targets_history import check_target_file_versions, serialize_target_file
from taf.tests.test_targets_history.conftest import (
    TARGET_NAME,
    make_entry,
    make_history,
)

HISTORY = make_history(4)
AUTH_COMMITS = [f"auth-commit-{index}" for index in range(10)]


def _versions(*contents):
    """(authentication commit, raw content) pairs for consecutive commits."""
    return [
        (auth_commit, None if content is None else serialize_target_file(content))
        for auth_commit, content in zip(AUTH_COMMITS, contents)
    ]


def test_check_versions_of_list_appended_one_commit_at_a_time():
    check_target_file_versions(
        TARGET_NAME,
        _versions(HISTORY[:1], HISTORY[:1], HISTORY[:2], HISTORY[:3], HISTORY),
    )


def test_check_versions_of_single_object_target_file_is_not_parsed():
    versions = [
        ("auth-commit-0", '{"not": valid json'),
        ("auth-commit-1", "{also not json"),
    ]

    check_target_file_versions(TARGET_NAME, versions, previous="{previous}")


def test_check_versions_parses_each_list_version_once(monkeypatch):
    loaded = []
    load = targets_history._load

    def counting_load(raw, target_name):
        loaded.append(raw)
        return load(raw, target_name)

    monkeypatch.setattr(targets_history, "_load", counting_load)

    check_target_file_versions(
        TARGET_NAME,
        _versions(HISTORY[:1], HISTORY[:1], HISTORY[:1], HISTORY[:2], HISTORY[:2]),
    )

    assert loaded == [
        None,
        serialize_target_file(HISTORY[:1]),
        serialize_target_file(HISTORY[:2]),
    ]


def test_check_versions_compares_first_version_with_previous():
    with pytest.raises(TargetsHistoryRewrittenError, match="at most one") as error:
        check_target_file_versions(
            TARGET_NAME,
            _versions(HISTORY[:3]),
            previous=serialize_target_file(HISTORY[:1]),
        )

    assert error.value.auth_commit == AUTH_COMMITS[0]


def test_check_versions_of_new_list_target_file():
    check_target_file_versions(TARGET_NAME, _versions(None, HISTORY[:1], HISTORY[:2]))

    with pytest.raises(TargetsHistoryRewrittenError, match="a new target file"):
        check_target_file_versions(TARGET_NAME, _versions(HISTORY[:2]))


def test_check_versions_allows_removed_and_readded_list_target_file():
    check_target_file_versions(
        TARGET_NAME,
        _versions(HISTORY[:1], HISTORY[:2], None, [make_entry("readded")]),
    )


@pytest.mark.parametrize(
    "contents, failing_index, reason",
    [
        (
            (HISTORY[:1], HISTORY[:2], [HISTORY[1], HISTORY[0]]),
            2,
            "previously listed commits were modified",
        ),
        ((HISTORY[:1], HISTORY[:2], HISTORY[:1]), 2, "were removed"),
        ((HISTORY[:1], make_entry("single")), 1, "replaced by a single commit"),
        (
            (make_entry("single"), HISTORY[:1]),
            1,
            "single commit was replaced by a list",
        ),
        ((HISTORY[:1], HISTORY[:1], HISTORY[:3]), 2, "at most one"),
    ],
    ids=[
        "commits-reordered",
        "commits-removed",
        "list-replaced-by-single-object",
        "single-object-replaced-by-list",
        "two-commits-appended",
    ],
)
def test_check_versions_rejects_rewritten_target_file(contents, failing_index, reason):
    with pytest.raises(TargetsHistoryRewrittenError, match=reason) as error:
        check_target_file_versions(TARGET_NAME, _versions(*contents))

    assert error.value.auth_commit == AUTH_COMMITS[failing_index]
    assert str(error.value).startswith(
        f"Target file {TARGET_NAME} was rewritten at commit {AUTH_COMMITS[failing_index]}: "
    )


def test_check_versions_rejects_invalid_list_target_file():
    versions = _versions(HISTORY[:1]) + [("auth-commit-1", "[not valid json")]

    with pytest.raises(InvalidTargetFileError, match="not valid JSON") as error:
        check_target_file_versions(TARGET_NAME, versions)

    assert error.value.auth_commit == "auth-commit-1"
