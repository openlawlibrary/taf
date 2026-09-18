"""TargetCommitMismatchError: message format and compatibility with the updater's error patterns."""

import re

import pytest

from taf.exceptions import TargetCommitMismatchError, UpdateFailedError
from taf.tests.test_updater.conftest import (
    TARGET_ADDITIONAL_COMMIT_PATTERN,
    TARGET_COMMIT_MISMATCH_PATTERN,
    TARGET_COMMIT_NOT_ON_BRANCH_PATTERN,
    TARGET_MISSING_COMMIT_PATTERN,
    TARGET_MISSMATCH_PATTERN,
)
from taf.tests.test_updater.test_target_validator.conftest import (
    AUTH_COMMIT_DATE,
    AUTH_REPO_NAME,
    MAIN,
    REPO1,
    UnauthenticatedPolicy,
    law,
    make_commits,
    validate,
)
from taf.updater.target_validator import TargetValidator


def _updater_error(error: Exception) -> str:
    """The message the updater reports for an error raised while updating the test auth repo."""
    return f"Update of {AUTH_REPO_NAME} failed due to error: {error}"


@pytest.fixture
def mismatch_error():
    """Error raised when a target repository skips ahead of its declared commit."""
    main = make_commits(MAIN, 3)
    steps = law({REPO1: (MAIN, main[0])}, {REPO1: (MAIN, main[2])})
    return validate(steps, {REPO1: {MAIN: main}}).error


@pytest.fixture
def not_on_branch_error():
    """Error raised when a declared commit is not on its branch."""
    main = make_commits(MAIN, 3)
    missing = make_commits("missing", 1)[0]
    steps = law({REPO1: (MAIN, main[0])}, {REPO1: (MAIN, missing)})
    return validate(
        steps,
        {REPO1: {MAIN: main}},
        is_unauthenticated_allowed=UnauthenticatedPolicy([REPO1]),
    ).error


def test_target_commit_mismatch_error_message_when_repository_at_other_commit():
    auth_commit, expected, actual = make_commits("message", 3)

    error = TargetCommitMismatchError(
        auth_repo_name=AUTH_REPO_NAME,
        auth_commit=auth_commit,
        commit_date=AUTH_COMMIT_DATE,
        repo_name=REPO1,
        expected_commit=expected,
        branch=MAIN,
        actual_commit=actual,
    )

    assert str(error) == (
        f"Failure to validate {AUTH_REPO_NAME} commit {auth_commit} committed on "
        f"{AUTH_COMMIT_DATE}: data repository {REPO1} was supposed to be at commit "
        f"{expected} but repo was at {actual}"
    )


def test_target_commit_mismatch_error_message_when_commit_not_on_branch():
    auth_commit, expected = make_commits("message", 2)

    error = TargetCommitMismatchError(
        auth_repo_name=AUTH_REPO_NAME,
        auth_commit=auth_commit,
        commit_date=AUTH_COMMIT_DATE,
        repo_name=REPO1,
        expected_commit=expected,
        branch=MAIN,
    )

    assert str(error) == (
        f"Failure to validate {AUTH_REPO_NAME} commit {auth_commit} committed on "
        f"{AUTH_COMMIT_DATE}: data repository {REPO1} was supposed to be at commit "
        f"{expected} but commit not on branch {MAIN}"
    )


def test_target_commit_mismatch_error_is_update_failed_error(mismatch_error):
    assert isinstance(mismatch_error, UpdateFailedError)
    with pytest.raises(UpdateFailedError):
        raise mismatch_error


def test_validator_error_uses_failing_auth_commit_date():
    main = make_commits(MAIN, 3)
    steps = law({REPO1: (MAIN, main[0])}, {REPO1: (MAIN, main[2])})
    requested = []

    def get_commit_date(auth_commit):
        requested.append(auth_commit)
        return AUTH_COMMIT_DATE

    error = (
        TargetValidator(
            steps,
            {REPO1: {MAIN: main}},
            auth_repo_name=AUTH_REPO_NAME,
            get_commit_date=get_commit_date,
        )
        .validate()
        .error
    )

    assert requested == [steps[1].auth_commit]
    assert error.commit_date == AUTH_COMMIT_DATE


@pytest.mark.parametrize(
    "pattern",
    [TARGET_MISSMATCH_PATTERN, TARGET_COMMIT_MISMATCH_PATTERN],
    ids=["TARGET_MISSMATCH_PATTERN", "TARGET_COMMIT_MISMATCH_PATTERN"],
)
def test_mismatch_error_matches_updater_pattern(mismatch_error, pattern):
    assert re.match(pattern, _updater_error(mismatch_error))


@pytest.mark.parametrize(
    "pattern",
    [
        TARGET_ADDITIONAL_COMMIT_PATTERN,
        TARGET_COMMIT_MISMATCH_PATTERN,
        TARGET_COMMIT_NOT_ON_BRANCH_PATTERN,
        TARGET_MISSING_COMMIT_PATTERN,
    ],
    ids=[
        "TARGET_ADDITIONAL_COMMIT_PATTERN",
        "TARGET_COMMIT_MISMATCH_PATTERN",
        "TARGET_COMMIT_NOT_ON_BRANCH_PATTERN",
        "TARGET_MISSING_COMMIT_PATTERN",
    ],
)
def test_not_on_branch_error_matches_updater_pattern(not_on_branch_error, pattern):
    assert re.match(pattern, _updater_error(not_on_branch_error))
