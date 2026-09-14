"""
Validation of target repositories' commits against the commits that an
authentication repository declares for them.

Each authentication commit (a "law step") declares a branch and commit for some
of the target repositories. Walking the steps in order, a target repository's
pointer may either stay where it is or move to the next commit on the declared
branch. Moving further than that means that the target repository contains
commits that were never authenticated, which is only allowed for repositories
that permit unauthenticated commits.

Each (repository, branch) pair is validated as a separate commit sequence, so
repositories that move between branches (e.g. publication branches) need no
special handling.

This module does not touch git. Callers provide the declared pointers, the
target repositories' commits and callbacks for anything that needs to be looked
up in the authentication repository.
"""

from typing import Callable, Dict, List, Mapping, Optional, Sequence, Tuple

import attrs

from taf.exceptions import TargetCommitMismatchError
from taf.log import taf_logger
from taf.models.types import Commitish


@attrs.frozen
class TargetPointer:
    """Branch and commit of a target repository."""

    branch: str
    commit: Commitish


@attrs.frozen
class LawStep:
    """
    An authentication commit and the pointers it declares, keyed by target
    repository name. Repositories without a target file at that commit are omitted.
    """

    auth_commit: Commitish
    targets: Mapping[str, TargetPointer]


@attrs.define
class ValidationResult:
    """
    Outcome of a validation run. If validation failed, `error` is set and the
    other fields contain everything that was validated before the failure.
    """

    validated_auth_commits: List[Commitish] = attrs.Factory(list)
    validated_commits_per_repo_branch: Dict[str, Dict[str, List[Commitish]]] = (
        attrs.Factory(dict)
    )
    last_validated_per_repo: Dict[str, TargetPointer] = attrs.Factory(dict)
    error: Optional[Exception] = None

    @property
    def succeeded(self) -> bool:
        return self.error is None


class TargetValidator:
    def __init__(
        self,
        steps: Sequence[LawStep],
        actual: Mapping[str, Mapping[str, Sequence[Commitish]]],
        start: Optional[Mapping[str, TargetPointer]] = None,
        is_unauthenticated_allowed: Optional[Callable[[str, Commitish], bool]] = None,
        auth_repo_name: str = "",
        get_commit_date: Optional[Callable[[Commitish], str]] = None,
    ):
        """
        Arguments:
            steps: Authentication commits to validate, oldest first.
            actual: Commits of each target repository's branches, oldest first,
                keyed by repository name and then branch name.
            start: Last validated pointer of each target repository. Repositories
                that were never validated are omitted.
            is_unauthenticated_allowed: Called with a repository name and an
                authentication commit when a target repository skips ahead.
                Returns whether that repository may contain unauthenticated
                commits as of that authentication commit. Defaults to never.
            auth_repo_name: Authentication repository name, used in error messages.
            get_commit_date: Returns the date of an authentication commit, used in
                error messages.
        """
        self.steps = steps
        self.actual = actual
        self.start = start or {}
        self.is_unauthenticated_allowed = is_unauthenticated_allowed or (
            lambda _repo_name, _auth_commit: False
        )
        self.auth_repo_name = auth_repo_name
        self.get_commit_date = get_commit_date or (lambda _auth_commit: "")
        self._positions: Dict[Tuple[str, str], Dict[Commitish, int]] = {}

    def validate(self) -> ValidationResult:
        """
        Validate all steps in order, stopping at the first failure. Never raises;
        a failure is returned in `ValidationResult.error`.
        """
        result = ValidationResult()
        try:
            for step in self.steps:
                for repo_name, declared in step.targets.items():
                    previous = result.last_validated_per_repo.get(
                        repo_name, self.start.get(repo_name)
                    )
                    self._validate_target(
                        step.auth_commit, repo_name, previous, declared
                    )
                    result.last_validated_per_repo[repo_name] = declared
                    result.validated_commits_per_repo_branch.setdefault(
                        repo_name, {}
                    ).setdefault(declared.branch, []).append(declared.commit)
                result.validated_auth_commits.append(step.auth_commit)
        except Exception as e:
            result.error = e
        return result

    def _validate_target(
        self,
        auth_commit: Commitish,
        repo_name: str,
        previous: Optional[TargetPointer],
        declared: TargetPointer,
    ) -> None:
        if previous is not None and declared.commit == previous.commit:
            return

        branch_commits = self.actual.get(repo_name, {}).get(declared.branch, [])
        next_index: Optional[int]
        if previous is not None and previous.branch == declared.branch:
            previous_index = self._position(repo_name, declared.branch, previous.commit)
            next_index = previous_index + 1 if previous_index is not None else None
        else:
            next_index = 0

        if next_index is None or next_index >= len(branch_commits):
            raise self._error(auth_commit, repo_name, declared)

        next_commit = branch_commits[next_index]
        if next_commit == declared.commit:
            return

        if not self.is_unauthenticated_allowed(repo_name, auth_commit):
            raise self._error(
                auth_commit, repo_name, declared, actual_commit=next_commit
            )

        declared_index = self._find(
            repo_name, declared.branch, declared.commit, next_index
        )
        if declared_index is None:
            raise self._error(auth_commit, repo_name, declared)
        taf_logger.debug(
            f"{repo_name}: skipped {declared_index - next_index} unauthenticated "
            f"commit(s) on branch {declared.branch} before commit {declared.commit}"
        )

    def _position(
        self, repo_name: str, branch: str, commit: Commitish
    ) -> Optional[int]:
        """Index of the first occurrence of `commit` on the branch, if present."""
        key = (repo_name, branch)
        positions = self._positions.get(key)
        if positions is None:
            positions = {}
            branch_commits = self.actual.get(repo_name, {}).get(branch, [])
            for index, branch_commit in enumerate(branch_commits):
                positions.setdefault(branch_commit, index)
            self._positions[key] = positions
        return positions.get(commit)

    def _find(
        self, repo_name: str, branch: str, commit: Commitish, from_index: int
    ) -> Optional[int]:
        """Index of the first occurrence of `commit` at or after `from_index`."""
        index = self._position(repo_name, branch, commit)
        if index is None:
            return None
        if index >= from_index:
            return index
        branch_commits = self.actual[repo_name][branch]
        for index in range(from_index, len(branch_commits)):
            if branch_commits[index] == commit:
                return index
        return None

    def _error(
        self,
        auth_commit: Commitish,
        repo_name: str,
        declared: TargetPointer,
        actual_commit: Optional[Commitish] = None,
    ) -> TargetCommitMismatchError:
        return TargetCommitMismatchError(
            auth_repo_name=self.auth_repo_name,
            auth_commit=auth_commit,
            commit_date=self.get_commit_date(auth_commit),
            repo_name=repo_name,
            expected_commit=declared.commit,
            branch=declared.branch,
            actual_commit=actual_commit,
        )
