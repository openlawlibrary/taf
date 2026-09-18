"""Reading and writing target files in the single object and list formats."""

import json

import pytest

from taf.exceptions import InvalidTargetFileError
from taf.targets_history import (
    TargetEntry,
    get_tip,
    is_history,
    parse_target_file,
    serialize_target_file,
)
from taf.tests.test_targets_history.conftest import (
    MAIN,
    PUBLICATION,
    TARGET_NAME,
    make_entry,
    make_history,
)


def test_parse_single_object_target_file():
    content = make_entry(**{"build-date": "2026-01-15", "codified-date": "2026-01-10"})

    entries = parse_target_file(content, TARGET_NAME)

    assert entries == [
        TargetEntry(  # type: ignore[call-arg]
            commit=content["commit"],
            branch=MAIN,
            custom={"build-date": "2026-01-15", "codified-date": "2026-01-10"},
        )
    ]


def test_parse_single_object_target_file_without_branch():
    content = make_entry()
    del content["branch"]

    assert parse_target_file(content, TARGET_NAME)[0].branch is None


def test_parse_list_target_file_oldest_first():
    content = make_history(3)

    entries = parse_target_file(content, TARGET_NAME)

    assert [entry.commit for entry in entries] == [entry["commit"] for entry in content]
    assert all(entry.custom == {"build-date": "2026-01-15"} for entry in entries)


def test_parse_branch_id_and_capstone_separately_from_custom_data():
    content = [
        make_entry("first", **{"branch-id": "build-1"}),
        make_entry("last", **{"branch-id": "build-1", "capstone": True, "note": "x"}),
    ]

    first, last = parse_target_file(content, TARGET_NAME)

    assert (first.branch_id, first.capstone, first.custom) == ("build-1", False, {})
    assert (last.branch_id, last.capstone, last.custom) == (
        "build-1",
        True,
        {"note": "x"},
    )


@pytest.mark.parametrize(
    "content",
    [
        "a3f1c2",
        42,
        [],
        {"branch": MAIN},
        [make_entry("first"), {"branch": MAIN}],
        [{"branch": MAIN, "commit": 42}],
        ["a3f1c2"],
    ],
    ids=[
        "string",
        "number",
        "empty-list",
        "object-without-commit",
        "entry-without-commit",
        "entry-with-non-string-commit",
        "entry-not-an-object",
    ],
)
def test_parse_invalid_target_file(content):
    with pytest.raises(InvalidTargetFileError, match=TARGET_NAME):
        parse_target_file(content, TARGET_NAME)


def test_is_history():
    assert is_history(make_history(1))
    assert not is_history(make_entry())


def test_get_tip_of_single_object_target_file():
    content = make_entry(**{"build-date": "2026-01-15"})

    tip = get_tip(content, TARGET_NAME)
    tip["commit"] = "changed"

    assert get_tip(content, TARGET_NAME) == content


def test_get_tip_of_list_target_file_is_last_entry():
    content = make_history(2) + [make_entry("tip", PUBLICATION, capstone=True)]

    tip = get_tip(content, TARGET_NAME)
    tip["commit"] = "changed"

    assert get_tip(content, TARGET_NAME) == content[-1]


def test_get_tip_of_invalid_target_file():
    with pytest.raises(InvalidTargetFileError):
        get_tip([], TARGET_NAME)


def test_serialize_single_object_target_file_as_before():
    content = make_entry(**{"build-date": "2026-01-15"})

    assert serialize_target_file(content) == json.dumps(content, indent=4)


def test_serialize_list_target_file_one_entry_per_line():
    content = make_history(3)

    serialized = serialize_target_file(content)

    assert json.loads(serialized) == content
    assert serialized.splitlines() == [
        "[",
        *(json.dumps(entry, separators=(",", ":")) + "," for entry in content[:-1]),
        json.dumps(content[-1], separators=(",", ":")),
        "]",
    ]


def test_serialize_appended_entry_adds_one_line():
    content = make_history(3)

    before = serialize_target_file(content).splitlines()
    after = serialize_target_file(content + [make_entry("appended")]).splitlines()

    assert len(after) == len(before) + 1
    assert after[: len(before) - 2] == before[:-2]
