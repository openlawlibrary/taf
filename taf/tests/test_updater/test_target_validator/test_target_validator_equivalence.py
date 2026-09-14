"""
TargetValidator makes the same decision, with the same error message, as the updater's
existing per-commit check (`AuthenticationRepositoryUpdatePipeline._validate_current_repo_commit`)
for every combination of previous pointer, declared pointer and unauthenticated-commits policy.

Remove this module together with `_validate_current_repo_commit` once the pipeline uses
TargetValidator.
"""

import itertools
from types import SimpleNamespace

import pytest

from taf.exceptions import UpdateFailedError
from taf.tests.test_updater.test_target_validator.conftest import (
    AUTH_COMMIT_DATE,
    AUTH_REPO_NAME,
    MAIN,
    PUBLICATION,
    REPO1,
    UnauthenticatedPolicy,
    law,
    make_commits,
    validate,
)
from taf.updater.target_validator import TargetPointer
from taf.updater.updater_pipeline import AuthenticationRepositoryUpdatePipeline

MAIN_COMMITS = make_commits(MAIN, 3)
PUBLICATION_COMMITS = make_commits(PUBLICATION, 2)
MISSING_COMMIT = make_commits("missing", 1)[0]
ACTUAL = {REPO1: {MAIN: MAIN_COMMITS, PUBLICATION: PUBLICATION_COMMITS}}

POINTERS = {
    **{f"{MAIN}_{index}": (MAIN, commit) for index, commit in enumerate(MAIN_COMMITS)},
    f"{MAIN}_missing": (MAIN, MISSING_COMMIT),
    **{
        f"{PUBLICATION}_{index}": (PUBLICATION, commit)
        for index, commit in enumerate(PUBLICATION_COMMITS)
    },
    f"{PUBLICATION}_missing": (PUBLICATION, MISSING_COMMIT),
}
PREVIOUS = {"none": None, **POINTERS}


def _legacy_outcome(previous, declared, auth_commit, unauthenticated_allowed):
    """Decision of the updater's existing check: None if valid, otherwise the error message."""
    pipeline = SimpleNamespace(
        _is_unauthenticated_allowed_at=lambda _repository, _auth_commit: unauthenticated_allowed
    )
    auth_repo = SimpleNamespace(
        name=AUTH_REPO_NAME, get_commit_date=lambda _commit: AUTH_COMMIT_DATE
    )
    previous_branch, previous_commit = (
        previous if previous is not None else (None, None)
    )
    try:
        AuthenticationRepositoryUpdatePipeline._validate_current_repo_commit(
            pipeline,
            SimpleNamespace(name=REPO1),
            auth_repo,
            previous_branch,
            previous_commit,
            declared[0],
            declared[1],
            ACTUAL[REPO1],
            auth_commit,
        )
    except UpdateFailedError as e:
        return str(e)
    return None


def _validator_outcome(steps, previous, unauthenticated_allowed):
    """Decision of TargetValidator: None if valid, otherwise the error message."""
    start = {REPO1: TargetPointer(*previous)} if previous is not None else None
    policy = UnauthenticatedPolicy([REPO1] if unauthenticated_allowed else [])
    result = validate(steps, ACTUAL, start=start, is_unauthenticated_allowed=policy)
    return None if result.succeeded else str(result.error)


@pytest.mark.parametrize(
    "previous_label, declared_label, unauthenticated_allowed",
    list(itertools.product(PREVIOUS, POINTERS, [False, True])),
)
def test_validator_matches_updater_check(
    previous_label, declared_label, unauthenticated_allowed
):
    previous = PREVIOUS[previous_label]
    declared = POINTERS[declared_label]
    steps = law({REPO1: declared})

    assert _validator_outcome(
        steps, previous, unauthenticated_allowed
    ) == _legacy_outcome(
        previous, declared, steps[0].auth_commit, unauthenticated_allowed
    )
