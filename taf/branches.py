"""
Generic helpers for recognizing, ordering and tracking "batch" branches -
branches in an authentication repository whose commits each authenticate one
commit of one or more target repositories (e.g. speculative branches,
publication branches, or single-commit update branches).

These helpers are pattern-driven rather than hardcoded to any particular
naming convention: callers supply a `BranchPattern` built from a regular
expression with named capture groups, and that pattern is used both to
recognize matching branches and to order them (oldest/newest first) using
the values of its named groups.
"""

import os
from pathlib import Path
import re
from typing import List, Optional, Tuple

from taf.exceptions import GitError, RoleMetadataNotSameError
from taf.models.types import Commitish


class BranchPattern:
    """
    Wraps a compiled regular expression used to recognize and order a family
    of branch names (e.g. `^publication/(?P<pub_date>...)\\.(?P<spec_date>...)$`).

    The pattern's named capture groups, in the order in which they are
    defined, are used as the branch's sort key.
    """

    def __init__(self, pattern: str):
        self.pattern = pattern
        self._regex = re.compile(pattern)
        self._group_names = sorted(
            self._regex.groupindex, key=lambda name: self._regex.groupindex[name]
        )

    def has_group(self, name: str) -> bool:
        return name in self._regex.groupindex

    def matches(self, branch_name: str) -> bool:
        return self._regex.match(branch_name) is not None

    def group(self, branch_name: str, name: str) -> Optional[str]:
        match = self._regex.match(branch_name)
        if match is None:
            return None
        try:
            return match.group(name)
        except (IndexError, re.error):
            return None

    def sort_key(self, branch_name: str) -> Tuple[str, ...]:
        match = self._regex.match(branch_name)
        if match is None:
            return tuple()
        return tuple(match.group(name) or "" for name in self._group_names)

    def __repr__(self):
        return f"BranchPattern({self.pattern!r})"


def select_branches(
    repo,
    pattern: BranchPattern,
    group_by: Optional[str] = None,
    traverse_branch: Optional[str] = None,
    include_remotes: bool = True,
) -> List[str]:
    """
    Select the newest branch of `repo` matching `pattern` that is reachable
    from `traverse_branch` (the repository's default branch, if not given) -
    one branch overall, or one per distinct value of the `group_by` named
    group if given (e.g. one per role, for update branches).

    "Newest" is judged first by how recently the branch diverged from
    `traverse_branch`'s history, then by the pattern's sort key - this is
    what keeps a same-day branch cut off an older commit from outranking one
    cut off a more recent commit, regardless of name.
    """
    traverse_branch = traverse_branch or repo.default_branch

    if group_by is None:
        branch = repo.find_first_branch_matching_pattern(
            traverse_branch,
            pattern.matches,
            include_remotes=include_remotes,
            sort_key_func=pattern.sort_key,
        )
        return [branch] if branch else []

    all_branches = repo.branches(all=include_remotes, strip_remote=True)
    group_values: List[str] = sorted(
        {
            value
            for branch in all_branches
            if pattern.matches(branch)
            for value in [pattern.group(branch, group_by)]
            if value is not None
        }
    )

    selected = []
    for value in group_values:
        branch = repo.find_first_branch_matching_pattern(
            traverse_branch,
            lambda b, v=value: pattern.matches(b) and pattern.group(b, group_by) == v,
            include_remotes=include_remotes,
            sort_key_func=pattern.sort_key,
        )
        if branch:
            selected.append(branch)
    return sorted(selected, key=pattern.sort_key, reverse=True)


def role_metadata_version(auth_repo, role: str, commit: Optional[Commitish]) -> int:
    """Read the version of `role`'s metadata file at `commit` (0 if it did not exist)."""
    try:
        role_metadata_path = os.path.join("metadata", f"{role}.json")
        metadata = auth_repo.get_json(commit, role_metadata_path)
        return metadata["signed"]["version"]
    except (GitError, KeyError, TypeError):
        return 0


def updated_roles_at_commit(auth_repo, commit: Commitish) -> List[str]:
    """Return the names of the roles whose metadata file changed at `commit`."""
    updated_files = auth_repo.list_changed_files_at_revision(commit)
    return [
        Path(updated_file).stem
        for updated_file in updated_files
        if Path(updated_file).parent.name == "metadata"
    ]


def find_unmerged_auth_commits(
    auth_repo, branch: str, default_branch: Optional[str] = None
) -> List[Commitish]:
    """
    Return, oldest first, the commits of `branch` (an auth repo branch whose
    commits authenticate commits of one or more target repositories) which
    have not yet been merged into `default_branch`.

    A commit is unmerged if any role it touches has a higher metadata
    version on `branch` than on `default_branch` - auth commits are re-signed
    onto the default branch rather than fast-forwarded, so branch commits
    never become git-reachable from it, and metadata version is the only
    reliable "already merged" watermark. No particular role needs to be
    named: a commit's own changed metadata files say which roles it touched.

    Raises RoleMetadataNotSameError if a touched role's metadata content
    differs between `branch` and `default_branch` at the same version - that
    means it was independently modified on `default_branch` since `branch`
    was created, and none of `branch`'s commits can be safely merged.
    """
    default_branch = default_branch or auth_repo.default_branch
    all_branch_commits = auth_repo.commits_on_branch_and_not_other(
        branch, default_branch
    )
    if not len(all_branch_commits):
        return []

    default_commit = auth_repo.top_commit_of_branch(default_branch)
    unmerged_commits = []

    for commit in all_branch_commits:
        is_unmerged = False
        for role in updated_roles_at_commit(auth_repo, commit):
            metadata_path = f"metadata/{role}.json"
            default_version = role_metadata_version(auth_repo, role, default_commit)
            commit_version = role_metadata_version(auth_repo, role, commit)
            if commit_version > default_version:
                is_unmerged = True
            elif commit_version == default_version:
                if auth_repo.get_json(
                    default_commit, metadata_path
                ) != auth_repo.get_json(commit, metadata_path):
                    raise RoleMetadataNotSameError(
                        f"{metadata_path} modified on {default_branch}! Commits of "
                        f"branch {branch} cannot be merged"
                    )
        if not is_unmerged:
            break
        unmerged_commits.append(commit)

    return unmerged_commits[::-1]
