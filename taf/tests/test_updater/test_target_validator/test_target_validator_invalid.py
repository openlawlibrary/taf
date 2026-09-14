"""TargetValidator: target repository histories that do not match what the law steps declare."""

import pytest

from taf.tests.test_updater.test_target_validator.conftest import (
    MAIN,
    PUBLICATION,
    REPO1,
    REPO2,
    UnauthenticatedPolicy,
    assert_invalid,
    law,
    make_commits,
    validate,
)
from taf.updater.target_validator import TargetPointer


@pytest.mark.parametrize("skipped", [1, 2])
def test_validate_rejects_unauthenticated_commits(skipped):
    main = make_commits(MAIN, skipped + 2)
    steps = law({REPO1: (MAIN, main[0])}, {REPO1: (MAIN, main[-1])})

    result = validate(steps, {REPO1: {MAIN: main}})

    assert_invalid(result, steps[:1], steps[1], REPO1, actual_commit=main[1])


def test_validate_rejects_unauthenticated_commits_at_start_of_branch():
    main = make_commits(MAIN, 2)
    steps = law({REPO1: (MAIN, main[1])})

    result = validate(steps, {REPO1: {MAIN: main}})

    assert_invalid(result, [], steps[0], REPO1, actual_commit=main[0])


def test_validate_rejects_unauthenticated_commits_after_last_validated_commit():
    main = make_commits(MAIN, 4)
    steps = law({REPO1: (MAIN, main[3])})

    result = validate(
        steps, {REPO1: {MAIN: main}}, start={REPO1: TargetPointer(MAIN, main[1])}
    )

    assert_invalid(result, [], steps[0], REPO1, actual_commit=main[2])


def test_validate_rejects_unauthenticated_commits_after_branch_change():
    main = make_commits(MAIN, 1)
    publication = make_commits(PUBLICATION, 2)
    steps = law({REPO1: (MAIN, main[0])}, {REPO1: (PUBLICATION, publication[1])})

    result = validate(steps, {REPO1: {MAIN: main, PUBLICATION: publication}})

    assert_invalid(result, steps[:1], steps[1], REPO1, actual_commit=publication[0])


def test_validate_rejects_commit_past_end_of_branch():
    main = make_commits(MAIN, 2)
    missing = make_commits("missing", 1)[0]
    steps = law({REPO1: (MAIN, missing)})

    result = validate(
        steps, {REPO1: {MAIN: main}}, start={REPO1: TargetPointer(MAIN, main[1])}
    )

    assert_invalid(result, [], steps[0], REPO1)


@pytest.mark.parametrize(
    "unauthenticated_allowed, expected_actual_index",
    [(False, 1), (True, None)],
    ids=["unauthenticated-not-allowed", "unauthenticated-allowed"],
)
def test_validate_rejects_commit_not_on_branch(
    unauthenticated_allowed, expected_actual_index
):
    main = make_commits(MAIN, 3)
    missing = make_commits("missing", 1)[0]
    steps = law({REPO1: (MAIN, main[0])}, {REPO1: (MAIN, missing)})
    allowed = [REPO1] if unauthenticated_allowed else []

    result = validate(
        steps,
        {REPO1: {MAIN: main}},
        is_unauthenticated_allowed=UnauthenticatedPolicy(allowed),
    )

    expected_actual = (
        None if expected_actual_index is None else main[expected_actual_index]
    )
    assert_invalid(result, steps[:1], steps[1], REPO1, actual_commit=expected_actual)


def test_validate_rejects_branch_missing_from_target_repository():
    main = make_commits(MAIN, 1)
    publication = make_commits(PUBLICATION, 1)
    steps = law({REPO1: (MAIN, main[0])}, {REPO1: (PUBLICATION, publication[0])})

    result = validate(steps, {REPO1: {MAIN: main}})

    assert_invalid(result, steps[:1], steps[1], REPO1)


def test_validate_rejects_repository_without_commits():
    main = make_commits(MAIN, 1)
    steps = law({REPO1: (MAIN, main[0])})

    result = validate(steps, {})

    assert_invalid(result, [], steps[0], REPO1)


def test_validate_rejects_last_validated_commit_missing_from_branch():
    """E.g. the target repository's history was rewritten after the last validation."""
    main = make_commits(MAIN, 2)
    rewritten = make_commits("rewritten", 1)[0]
    steps = law({REPO1: (MAIN, main[1])})

    result = validate(
        steps, {REPO1: {MAIN: main}}, start={REPO1: TargetPointer(MAIN, rewritten)}
    )

    assert_invalid(result, [], steps[0], REPO1)


def test_validate_rejects_moving_back_to_earlier_commit():
    main = make_commits(MAIN, 3)
    steps = law(
        {REPO1: (MAIN, main[0])},
        {REPO1: (MAIN, main[1])},
        {REPO1: (MAIN, main[0])},
    )

    result = validate(steps, {REPO1: {MAIN: main}})

    assert_invalid(result, steps[:2], steps[2], REPO1, actual_commit=main[2])


def test_validate_rejects_moving_back_to_earlier_commit_when_unauthenticated_allowed():
    main = make_commits(MAIN, 3)
    steps = law(
        {REPO1: (MAIN, main[0])},
        {REPO1: (MAIN, main[1])},
        {REPO1: (MAIN, main[0])},
    )

    result = validate(
        steps,
        {REPO1: {MAIN: main}},
        is_unauthenticated_allowed=UnauthenticatedPolicy([REPO1]),
    )

    assert_invalid(result, steps[:2], steps[2], REPO1)


def test_validate_rejects_swapped_commits_when_unauthenticated_allowed():
    """
    With target commits swapped, the first out-of-order commit is accepted as a skip,
    but the commit it jumped over is then never found.
    """
    main = make_commits(MAIN, 3)
    swapped = [main[0], main[2], main[1]]
    steps = law(
        {REPO1: (MAIN, main[0])},
        {REPO1: (MAIN, main[1])},
        {REPO1: (MAIN, main[2])},
    )

    result = validate(
        steps,
        {REPO1: {MAIN: swapped}},
        is_unauthenticated_allowed=UnauthenticatedPolicy([REPO1]),
    )

    assert_invalid(result, steps[:2], steps[2], REPO1)


def test_validate_rejects_skip_after_unauthenticated_commits_are_disallowed():
    """Whether commits may be skipped is decided per authentication commit."""
    main = make_commits(MAIN, 5)
    steps = law(
        {REPO1: (MAIN, main[0])},
        {REPO1: (MAIN, main[2])},
        {REPO1: (MAIN, main[4])},
    )
    policy = UnauthenticatedPolicy([(REPO1, steps[1].auth_commit)])

    result = validate(steps, {REPO1: {MAIN: main}}, is_unauthenticated_allowed=policy)

    assert_invalid(result, steps[:2], steps[2], REPO1, actual_commit=main[3])
    assert policy.calls == [
        (REPO1, steps[1].auth_commit),
        (REPO1, steps[2].auth_commit),
    ]


def test_validate_stops_at_first_failure_and_keeps_progress():
    main = make_commits(MAIN, 5)
    steps = law(
        {REPO1: (MAIN, main[0])},
        {REPO1: (MAIN, main[1])},
        {REPO1: (MAIN, main[3])},
        {REPO1: (MAIN, main[4])},
    )

    result = validate(steps, {REPO1: {MAIN: main}})

    assert_invalid(result, steps[:2], steps[2], REPO1, actual_commit=main[2])
    assert result.validated_commits_per_repo_branch == {REPO1: {MAIN: main[:2]}}
    assert result.last_validated_per_repo == {REPO1: TargetPointer(MAIN, main[1])}


def test_validate_keeps_repositories_validated_before_failure_in_same_law_step():
    """
    Repositories are validated in declaration order within a law step. Those checked
    before the failing one keep that step's commit, but the authentication commit
    itself is not counted as validated (the updater's existing behaviour).
    """
    repo1_main = make_commits(f"{REPO1}-{MAIN}", 2)
    repo2_main = make_commits(f"{REPO2}-{MAIN}", 3)
    steps = law(
        {REPO1: (MAIN, repo1_main[0]), REPO2: (MAIN, repo2_main[0])},
        {REPO1: (MAIN, repo1_main[1]), REPO2: (MAIN, repo2_main[2])},
    )

    result = validate(steps, {REPO1: {MAIN: repo1_main}, REPO2: {MAIN: repo2_main}})

    assert_invalid(result, steps[:1], steps[1], REPO2, actual_commit=repo2_main[1])
    assert result.validated_commits_per_repo_branch == {
        REPO1: {MAIN: repo1_main},
        REPO2: {MAIN: [repo2_main[0]]},
    }
    assert result.last_validated_per_repo == {
        REPO1: TargetPointer(MAIN, repo1_main[1]),
        REPO2: TargetPointer(MAIN, repo2_main[0]),
    }


def test_validate_returns_unexpected_error_with_progress():
    main = make_commits(MAIN, 3)
    steps = law({REPO1: (MAIN, main[0])}, {REPO1: (MAIN, main[2])})

    def failing_policy(_repo_name, _auth_commit):
        raise RuntimeError("could not read repositories.json")

    result = validate(
        steps, {REPO1: {MAIN: main}}, is_unauthenticated_allowed=failing_policy
    )

    assert not result.succeeded
    assert isinstance(result.error, RuntimeError)
    assert result.validated_auth_commits == [steps[0].auth_commit]
    assert result.validated_commits_per_repo_branch == {REPO1: {MAIN: [main[0]]}}
