"""TargetValidator: target repository histories that match what the law steps declare."""

import pytest

from taf.tests.test_updater.test_target_validator.conftest import (
    MAIN,
    PUBLICATION,
    REPO1,
    REPO2,
    UnauthenticatedPolicy,
    assert_valid,
    law,
    make_commits,
    validate,
)
from taf.updater.target_validator import TargetPointer


def test_validate_without_steps():
    result = validate([], {REPO1: {MAIN: make_commits(MAIN, 2)}})

    assert_valid(result, [], {})
    assert result.last_validated_per_repo == {}


def test_validate_first_commit_of_repository_without_last_validated_commit():
    main = make_commits(MAIN, 1)
    steps = law({REPO1: (MAIN, main[0])})

    result = validate(steps, {REPO1: {MAIN: main}})

    assert_valid(result, steps, {REPO1: {MAIN: [main[0]]}})
    assert result.last_validated_per_repo == {REPO1: TargetPointer(MAIN, main[0])}


def test_validate_one_commit_per_law_step():
    main = make_commits(MAIN, 4)
    steps = law(*({REPO1: (MAIN, commit)} for commit in main))

    result = validate(steps, {REPO1: {MAIN: main}})

    assert_valid(result, steps, {REPO1: {MAIN: main}})
    assert result.last_validated_per_repo == {REPO1: TargetPointer(MAIN, main[-1])}


def test_validate_continues_from_last_validated_commit():
    main = make_commits(MAIN, 5)
    steps = law({REPO1: (MAIN, main[3])}, {REPO1: (MAIN, main[4])})

    result = validate(
        steps, {REPO1: {MAIN: main}}, start={REPO1: TargetPointer(MAIN, main[2])}
    )

    assert_valid(result, steps, {REPO1: {MAIN: main[3:]}})


def test_validate_last_validated_commit_redeclared():
    main = make_commits(MAIN, 3)
    steps = law({REPO1: (MAIN, main[1])})

    result = validate(
        steps, {REPO1: {MAIN: main}}, start={REPO1: TargetPointer(MAIN, main[1])}
    )

    assert_valid(result, steps, {REPO1: {MAIN: [main[1]]}})


def test_validate_records_unchanged_commit_once_per_law_step():
    """A law step that does not move a target still validates (and records) it."""
    main = make_commits(MAIN, 2)
    steps = law(
        {REPO1: (MAIN, main[0])},
        {REPO1: (MAIN, main[0])},
        {REPO1: (MAIN, main[1])},
    )

    result = validate(steps, {REPO1: {MAIN: main}})

    assert_valid(result, steps, {REPO1: {MAIN: [main[0], main[0], main[1]]}})


def test_validate_skips_repository_not_declared_in_law_step():
    main = make_commits(MAIN, 2)
    steps = law({REPO1: (MAIN, main[0])}, {}, {REPO1: (MAIN, main[1])})

    result = validate(steps, {REPO1: {MAIN: main}})

    assert_valid(result, steps, {REPO1: {MAIN: main}})


def test_validate_repositories_independently():
    repo1_main = make_commits(f"{REPO1}-{MAIN}", 3)
    repo2_main = make_commits(f"{REPO2}-{MAIN}", 2)
    steps = law(
        {REPO1: (MAIN, repo1_main[0]), REPO2: (MAIN, repo2_main[0])},
        {REPO1: (MAIN, repo1_main[1]), REPO2: (MAIN, repo2_main[0])},
        {REPO1: (MAIN, repo1_main[2]), REPO2: (MAIN, repo2_main[1])},
    )

    result = validate(steps, {REPO1: {MAIN: repo1_main}, REPO2: {MAIN: repo2_main}})

    assert_valid(
        result,
        steps,
        {
            REPO1: {MAIN: repo1_main},
            REPO2: {MAIN: [repo2_main[0], repo2_main[0], repo2_main[1]]},
        },
    )
    assert result.last_validated_per_repo == {
        REPO1: TargetPointer(MAIN, repo1_main[2]),
        REPO2: TargetPointer(MAIN, repo2_main[1]),
    }


def test_validate_repository_added_in_later_law_step():
    repo1_main = make_commits(f"{REPO1}-{MAIN}", 2)
    repo2_main = make_commits(f"{REPO2}-{MAIN}", 1)
    steps = law(
        {REPO1: (MAIN, repo1_main[0])},
        {REPO1: (MAIN, repo1_main[1]), REPO2: (MAIN, repo2_main[0])},
    )

    result = validate(steps, {REPO1: {MAIN: repo1_main}, REPO2: {MAIN: repo2_main}})

    assert_valid(result, steps, {REPO1: {MAIN: repo1_main}, REPO2: {MAIN: repo2_main}})


def test_validate_branch_change_starts_from_first_commit_of_new_branch():
    main = make_commits(MAIN, 2)
    publication = make_commits(PUBLICATION, 2)
    steps = law(
        {REPO1: (MAIN, main[0])},
        {REPO1: (MAIN, main[1])},
        {REPO1: (PUBLICATION, publication[0])},
        {REPO1: (PUBLICATION, publication[1])},
    )

    result = validate(steps, {REPO1: {MAIN: main, PUBLICATION: publication}})

    assert_valid(result, steps, {REPO1: {MAIN: main, PUBLICATION: publication}})
    assert result.last_validated_per_repo == {
        REPO1: TargetPointer(PUBLICATION, publication[1])
    }


def test_validate_branch_change_from_last_validated_commit():
    main = make_commits(MAIN, 2)
    publication = make_commits(PUBLICATION, 1)
    steps = law({REPO1: (PUBLICATION, publication[0])})

    result = validate(
        steps,
        {REPO1: {MAIN: main, PUBLICATION: publication}},
        start={REPO1: TargetPointer(MAIN, main[1])},
    )

    assert_valid(result, steps, {REPO1: {PUBLICATION: publication}})


def test_validate_return_to_earlier_branch_continues_after_its_last_validated_commit():
    main = make_commits(MAIN, 2)
    publication = make_commits(PUBLICATION, 1)
    steps = law(
        {REPO1: (MAIN, main[0])},
        {REPO1: (PUBLICATION, publication[0])},
        {REPO1: (MAIN, main[1])},
    )

    result = validate(steps, {REPO1: {MAIN: main, PUBLICATION: publication}})

    assert_valid(result, steps, {REPO1: {MAIN: main, PUBLICATION: publication}})


def test_validate_return_to_earlier_branch_at_commit_it_was_left_at():
    main = make_commits(MAIN, 2)
    publication = make_commits(PUBLICATION, 1)
    steps = law(
        {REPO1: (MAIN, main[0])},
        {REPO1: (PUBLICATION, publication[0])},
        {REPO1: (MAIN, main[0])},
    )

    result = validate(steps, {REPO1: {MAIN: main, PUBLICATION: publication}})

    assert_valid(
        result,
        steps,
        {REPO1: {MAIN: [main[0], main[0]], PUBLICATION: publication}},
    )


def test_validate_return_to_branch_of_last_validated_commit():
    main = make_commits(MAIN, 3)
    publication = make_commits(PUBLICATION, 1)
    steps = law({REPO1: (PUBLICATION, publication[0])}, {REPO1: (MAIN, main[2])})

    result = validate(
        steps,
        {REPO1: {MAIN: main, PUBLICATION: publication}},
        start={REPO1: TargetPointer(MAIN, main[1])},
    )

    assert_valid(result, steps, {REPO1: {MAIN: [main[2]], PUBLICATION: publication}})


def test_validate_same_commit_on_new_branch_containing_it():
    """A new branch can start at the commit the repository is already at."""
    main = make_commits(MAIN, 1)
    publication = [main[0]] + make_commits(PUBLICATION, 1)
    steps = law(
        {REPO1: (MAIN, main[0])},
        {REPO1: (PUBLICATION, main[0])},
        {REPO1: (PUBLICATION, publication[1])},
    )

    result = validate(steps, {REPO1: {MAIN: main, PUBLICATION: publication}})

    assert_valid(result, steps, {REPO1: {MAIN: main, PUBLICATION: publication}})


@pytest.mark.parametrize("skipped", [1, 2, 5])
def test_validate_skips_unauthenticated_commits_when_allowed(skipped):
    main = make_commits(MAIN, skipped + 2)
    steps = law({REPO1: (MAIN, main[0])}, {REPO1: (MAIN, main[-1])})

    result = validate(
        steps,
        {REPO1: {MAIN: main}},
        is_unauthenticated_allowed=UnauthenticatedPolicy([REPO1]),
    )

    assert_valid(result, steps, {REPO1: {MAIN: [main[0], main[-1]]}})


def test_validate_skips_unauthenticated_commits_at_start_of_branch_when_allowed():
    main = make_commits(MAIN, 3)
    steps = law({REPO1: (MAIN, main[2])})

    result = validate(
        steps,
        {REPO1: {MAIN: main}},
        is_unauthenticated_allowed=UnauthenticatedPolicy([REPO1]),
    )

    assert_valid(result, steps, {REPO1: {MAIN: [main[2]]}})


def test_validate_skips_unauthenticated_commits_after_last_validated_commit_when_allowed():
    main = make_commits(MAIN, 5)
    steps = law({REPO1: (MAIN, main[4])})

    result = validate(
        steps,
        {REPO1: {MAIN: main}},
        start={REPO1: TargetPointer(MAIN, main[1])},
        is_unauthenticated_allowed=UnauthenticatedPolicy([REPO1]),
    )

    assert_valid(result, steps, {REPO1: {MAIN: [main[4]]}})


def test_validate_checks_unauthenticated_policy_only_when_commits_are_skipped():
    main = make_commits(MAIN, 4)
    steps = law(
        {REPO1: (MAIN, main[0])},
        {REPO1: (MAIN, main[0])},
        {REPO1: (MAIN, main[1])},
        {REPO1: (MAIN, main[3])},
    )
    policy = UnauthenticatedPolicy([REPO1])

    result = validate(steps, {REPO1: {MAIN: main}}, is_unauthenticated_allowed=policy)

    assert result.succeeded
    assert policy.calls == [(REPO1, steps[3].auth_commit)]


def test_validate_unauthenticated_policy_is_scoped_to_repository():
    repo1_main = make_commits(f"{REPO1}-{MAIN}", 3)
    repo2_main = make_commits(f"{REPO2}-{MAIN}", 2)
    steps = law(
        {REPO1: (MAIN, repo1_main[0]), REPO2: (MAIN, repo2_main[0])},
        {REPO1: (MAIN, repo1_main[2]), REPO2: (MAIN, repo2_main[1])},
    )
    policy = UnauthenticatedPolicy([REPO1])

    result = validate(
        steps,
        {REPO1: {MAIN: repo1_main}, REPO2: {MAIN: repo2_main}},
        is_unauthenticated_allowed=policy,
    )

    assert result.succeeded
    assert policy.calls == [(REPO1, steps[1].auth_commit)]


def test_validate_finds_repeated_commit_after_pointer_when_allowed():
    """If a commit is listed more than once, the occurrence after the pointer is used."""
    main = make_commits(MAIN, 4)
    branch_commits = [main[0], main[1], main[2], main[3], main[1]]
    steps = law({REPO1: (MAIN, main[2])}, {REPO1: (MAIN, main[1])})

    result = validate(
        steps,
        {REPO1: {MAIN: branch_commits}},
        start={REPO1: TargetPointer(MAIN, main[0])},
        is_unauthenticated_allowed=UnauthenticatedPolicy([REPO1]),
    )

    assert_valid(result, steps, {REPO1: {MAIN: [main[2], main[1]]}})
