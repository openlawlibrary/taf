"""Builders for TargetValidator unit tests.

Tests describe a scenario as the commits of each target repository's branches and
a sequence of law steps (authentication commits), each declaring a branch and
commit per target repository. No git repositories are involved.
"""

import hashlib
from typing import Callable, Dict, Iterable, List, Mapping, Optional, Tuple, Union

from taf.exceptions import TargetCommitMismatchError
from taf.models.types import Commitish
from taf.updater.target_validator import (
    LawStep,
    TargetPointer,
    TargetValidator,
    ValidationResult,
)

AUTH_REPO_NAME = "namespace/auth"
AUTH_COMMIT_DATE = "2026-01-15"
REPO1 = "namespace/repo1"
REPO2 = "namespace/repo2"
MAIN = "main"
PUBLICATION = "publication"

Declaration = Tuple[str, Commitish]


def make_commits(label: str, count: int) -> List[Commitish]:
    """Deterministic, distinct 40-character commit SHAs, e.g. make_commits("main", 3)."""
    return [
        Commitish.from_hash(
            hashlib.sha1(f"{label}-{index}".encode(), usedforsecurity=False).hexdigest()
        )
        for index in range(count)
    ]


def law(*declarations: Mapping[str, Declaration]) -> List[LawStep]:
    """
    Build consecutive law steps, one per declaration. Each declaration maps target
    repository names to the (branch, commit) declared at that step, e.g.

        law({REPO1: (MAIN, main[0])}, {REPO1: (MAIN, main[1]), REPO2: (MAIN, other[0])})
    """
    auth_commits = make_commits("auth", len(declarations))
    return [
        LawStep(  # type: ignore[call-arg]
            auth_commit=auth_commit,
            targets={
                repo_name: TargetPointer(branch, commit)  # type: ignore[call-arg]
                for repo_name, (branch, commit) in declaration.items()
            },
        )
        for auth_commit, declaration in zip(auth_commits, declarations)
    ]


class UnauthenticatedPolicy:
    """
    `is_unauthenticated_allowed` callback that records every call.

    `allowed` holds repository names (allowed at every authentication commit) and/or
    (repository name, authentication commit) pairs (allowed only at that commit).
    """

    def __init__(self, allowed: Iterable[Union[str, Tuple[str, Commitish]]] = ()):
        self.allowed = set(allowed)
        self.calls: List[Tuple[str, Commitish]] = []

    def __call__(self, repo_name: str, auth_commit: Commitish) -> bool:
        self.calls.append((repo_name, auth_commit))
        return repo_name in self.allowed or (repo_name, auth_commit) in self.allowed


def validate(
    steps: List[LawStep],
    actual: Mapping[str, Mapping[str, List[Commitish]]],
    start: Optional[Mapping[str, TargetPointer]] = None,
    is_unauthenticated_allowed: Optional[Callable[[str, Commitish], bool]] = None,
) -> ValidationResult:
    """Run TargetValidator with the test authentication repository's name and commit date."""
    return TargetValidator(
        steps,
        actual,
        start=start,
        is_unauthenticated_allowed=is_unauthenticated_allowed,
        auth_repo_name=AUTH_REPO_NAME,
        get_commit_date=lambda _auth_commit: AUTH_COMMIT_DATE,
    ).validate()


def assert_valid(
    result: ValidationResult,
    steps: List[LawStep],
    validated_commits: Dict[str, Dict[str, List[Commitish]]],
) -> None:
    """Every step validated, with exactly these commits recorded per repository and branch."""
    assert result.error is None
    assert result.succeeded
    assert result.validated_auth_commits == [step.auth_commit for step in steps]
    assert result.validated_commits_per_repo_branch == validated_commits


def assert_invalid(
    result: ValidationResult,
    validated_steps: List[LawStep],
    failed_step: LawStep,
    repo_name: str,
    actual_commit: Optional[Commitish] = None,
) -> None:
    """
    Validation stopped at `failed_step` because of `repo_name`, after validating
    `validated_steps`. `actual_commit` is None when the declared commit was not
    found on its branch, otherwise the commit the repository was at instead.
    """
    assert not result.succeeded
    assert isinstance(result.error, TargetCommitMismatchError)
    assert result.validated_auth_commits == [
        step.auth_commit for step in validated_steps
    ]
    declared = failed_step.targets[repo_name]
    assert result.error.auth_commit == failed_step.auth_commit
    assert result.error.repo_name == repo_name
    assert result.error.expected_commit == declared.commit
    assert result.error.branch == declared.branch
    assert result.error.actual_commit == actual_commit
