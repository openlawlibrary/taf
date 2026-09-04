"""
Merges commits of a "batch" branch in an authentication repository - a
branch whose commits each authenticate one commit of one or more target
repositories, such as a speculative branch, a publication branch, or a
single-commit update branch - into each repository's destination branch.

Which target repositories participate, what commit each one merges to, its
destination branch and any date gate are all read directly from the auth
repo's signed target files at each unmerged commit (`taf.branches`); nothing
about a specific repository needs to be configured. What is not in that data
- branch name patterns, capstone role policy - comes from a `MergePolicy`
(`taf.models.merge`).
"""

import datetime as dt
from pathlib import Path
from logging import ERROR, INFO
from typing import Dict, Iterable, List, Optional, Set, Tuple

from logdecorator import log_on_end, log_on_error, log_on_start

import taf.repositoriesdb as repositoriesdb
from taf.api.metadata import update_snapshot_and_timestamp
from taf.auth_repo import AuthenticationRepository
from taf.branches import (
    BranchPattern,
    find_unmerged_auth_commits,
    select_branches,
    updated_roles_at_commit,
)
from taf.exceptions import (
    GitError,
    InvalidBranchError,
    MergeError,
    RoleMetadataNotSameError,
    TAFError,
    ValidationFailedError,
)
from taf.git import GitRepository
from taf.git_providers import get_git_provider
from taf.log import taf_logger
from taf.models.merge import MergePolicy
from taf.models.types import Commitish
from taf.updater.updater import validate_repository
from taf.validation import validate_branch
from taf.yubikey.yubikey_manager import PinManager


class MergeStep:
    def __init__(
        self, auth_commit: Commitish, targets: Optional[Dict[str, Dict]] = None
    ):
        self.auth_commit = auth_commit
        self.targets: Dict[str, Dict] = targets if targets is not None else {}


class MergeResult:
    """
    What `merge_branch_commits` did.

    merged_branches
        Names of the source branches that had at least one commit merged.
    moved_repos
        Names of the target repositories whose destination branch moved.
    signed_commits
        Total number of auth repo commits re-signed onto the default branch.
    """

    def __init__(
        self,
        merged_branches: Optional[List[str]] = None,
        moved_repos: Optional[List[str]] = None,
        signed_commits: int = 0,
    ):
        self.merged_branches: List[str] = (
            list(merged_branches) if merged_branches else []
        )
        self.moved_repos: List[str] = list(moved_repos) if moved_repos else []
        self.signed_commits: int = signed_commits

    def __repr__(self) -> str:
        return (
            f"MergeResult(merged_branches={self.merged_branches!r}, "
            f"moved_repos={self.moved_repos!r}, signed_commits={self.signed_commits})"
        )


def _sign_and_merge_commit(
    auth_repo: AuthenticationRepository,
    commit: Commitish,
    roles: Iterable[str],
    keystore: Optional[str],
) -> None:
    """
    Checkout the changes made to `roles`' target files at `commit` onto the
    currently checked out branch of `auth_repo`, then re-sign snapshot and
    timestamp and commit.
    """
    roles = list(roles)
    taf_logger.info(f"Merging commit {commit} into {auth_repo.name}")
    changed_files = auth_repo.list_changed_files_at_revision(commit)
    for changed_file in changed_files:
        changed_file_path = Path(auth_repo.path, changed_file)
        try:
            changed_file_rel_path = changed_file_path.relative_to(
                auth_repo.targets_path
            )
            if (
                auth_repo.get_role_from_target_paths([str(changed_file_rel_path)])
                not in roles
            ):
                continue
        except ValueError:
            pass
        try:
            auth_repo.checkout_paths(commit, changed_file)
        except Exception:
            pass

    for role in roles:
        auth_repo.delete_unregistered_target_files(role)

    commit_msg = auth_repo.get_commit_message(commit)
    update_snapshot_and_timestamp(
        path=auth_repo.path,
        pin_manager=auth_repo.pin_manager,
        keystore=keystore,
        commit_msg=commit_msg,
        skip_clean_check=True,
        roles_to_sync=roles,
        push=False,
        skip_remote_check=True,
    )
    taf_logger.info("Updated snapshot and timestamp")


def _load_non_archived_repos(
    auth_repo, library_dir, commit
) -> Dict[str, GitRepository]:
    repositoriesdb.load_repositories(
        auth_repo, commits=[commit], library_dir=library_dir, only_load_targets=False
    )
    repos = repositoriesdb.get_repositories(auth_repo, commit)
    return {
        name: repo for name, repo in repos.items() if not repo.custom.get("archived")
    }


def _load_non_archived_repos_uncached(
    auth_repo, library_dir, commit
) -> Dict[str, GitRepository]:
    """
    Like `_load_non_archived_repos`, but bypasses repositoriesdb's process-wide cache.
    That cache is keyed only by (auth repo path, commit): whichever caller loads a
    commit first fixes the repo class for every later caller of that same commit, even
    one that needs a different `repo_classes`. Used for a check that runs on every
    `merge_branch_commits` call regardless of new work, so it must not be the one to
    win that race against a caller (e.g. platform's own repo-class loading) that needs
    a specific subclass for the same commit.
    """
    repos = repositoriesdb._load_repositories(
        auth_repo, library_dir=library_dir, commits=[commit], only_load_targets=False
    )
    return {
        name: repo
        for name, repo in repos.get(commit, {}).items()
        if not repo.custom.get("archived")
    }


def _build_steps(auth_repo, unmerged_auth_commits, repo_names) -> List[MergeStep]:
    steps = []
    for commit in unmerged_auth_commits:
        targets = {}
        for name in repo_names:
            target = auth_repo.get_target(name, commit)
            if target is not None:
                targets[name] = target
        steps.append(MergeStep(auth_commit=commit, targets=targets))
    return steps


def _last_qualifying_step_index(steps: List[MergeStep], gate: Optional[str]) -> int:
    """
    Index of the last step whose gate value (if any) is today or earlier.
    -1 if even the first step is gated into the future.
    """
    if gate is None:
        return len(steps) - 1
    today = dt.date.today().isoformat()
    last = -1
    for i, step in enumerate(steps):
        gate_values = {t[gate] for t in step.targets.values() if gate in t}
        if gate_values and max(gate_values) > today:
            break
        last = i
    return last


def _plan_merge(
    repos_by_name, final_step: MergeStep
) -> Dict[str, Tuple[str, Commitish]]:
    """
    For each repo with a target at `final_step`, decide whether its declared
    commit is new work: it participates if that commit is not yet reachable
    from its declared destination branch (a repo that was not touched by
    this batch of commits already points there and drops out on its own).
    """
    plan = {}
    for name, repo in repos_by_name.items():
        target = final_step.targets.get(name)
        if target is None:
            continue
        declared_commit = Commitish.from_hash(target["commit"])
        destination = target.get("branch") or repo.default_branch
        repo.create_local_branch_from_remote_tracking(destination)
        if repo.is_commit_an_ancestor_of_a_commit_or_branch(
            declared_commit, destination
        ):
            continue
        plan[name] = (destination, declared_commit)
    return plan


def _drop_or_reject_missing_commits(
    source_branch, merge_plan, repos_by_name
) -> Dict[str, Tuple[str, Commitish]]:
    """
    A repo whose local branch mirrors `source_branch` (speculative, rdf) moves in
    lockstep with the auth branch, so a declared commit missing from all of its
    branches is a corruption signal - typically a force push - and an error.

    A repo that does not mirror it (a single-commit update branch, whose commit is
    expected to already exist from a separate push) is not required to have that
    commit yet; if it does not, the repo is just not ready to merge, so it is
    dropped from the plan instead of raised.
    """
    filtered = {}
    for name, (destination, declared_commit) in merge_plan.items():
        repo = repos_by_name[name]
        if repo.branches_containing_commit(declared_commit):
            filtered[name] = (destination, declared_commit)
            continue
        if repo.branch_exists(source_branch):
            raise MergeError(
                f"{source_branch}: declared commit {declared_commit} for {name} no "
                "longer exists on any branch of that repository - check for a force push"
            )
        taf_logger.warning(
            f"{source_branch}: declared commit {declared_commit} for {name} not yet "
            "found on any branch of that repository - skipping"
        )
    return filtered


def _verify_previously_merged_repos_intact(
    auth_repo: AuthenticationRepository, default_branch: str, library_dir: Optional[str]
) -> None:
    """
    Every target repo already merged by a previous call must still contain, on its
    declared destination branch, the commit the auth repo's current default-branch
    state declares for it. This runs on every call, regardless of whether there is
    any new work to merge: a target repo's destination branch can be rewritten
    (a manual reset, or a force push straight to the destination rather than through
    a batch branch) at a time when no new batch touches that repo, and it should
    still be caught the next time this runs rather than only when new work for that
    repo happens to line up. Silently re-merging over a regressed destination would
    paper over the loss, so it is raised instead of healed.
    """
    top_commit = auth_repo.top_commit_of_branch(default_branch)
    if top_commit is None:
        return
    repos = _load_non_archived_repos_uncached(auth_repo, library_dir, top_commit)
    corrupted = []
    for name, repo in sorted(repos.items()):
        target = auth_repo.get_target(name, top_commit)
        if target is None:
            continue
        declared_commit = Commitish.from_hash(target["commit"])
        destination = target.get("branch") or repo.default_branch
        if destination is None:
            continue
        repo.create_local_branch_from_remote_tracking(destination)
        if not repo.is_commit_an_ancestor_of_a_commit_or_branch(
            declared_commit, destination
        ):
            corrupted.append(
                f"{name}: previously merged commit {declared_commit} is no longer an "
                f"ancestor of {destination} - that branch may have been rewritten "
                "since the last merge"
            )
    if corrupted:
        raise MergeError("\n".join(corrupted))


def _mirrored_repos(source_branch, merge_plan, repos_by_name, qualifying_steps, policy):
    """
    Repos whose local branch history actually mirrors `source_branch` -
    `validate_branch` walks them commit-for-commit against the auth branch, which
    only makes sense for a repo that carries one commit per qualifying step.

    If `policy.allow_uneven_branch_lengths`, a repo whose count differs from the
    step count (e.g. rdf carrying one extra rebuild commit) is excluded here and
    left to the post-merge repository validation instead. Otherwise an uneven
    count is left in and surfaces as a validation error - the ordinary signal
    that a repo's branch lost commits to a force push.
    """
    mirrored = [
        (name, destination)
        for name, (destination, _) in merge_plan.items()
        if repos_by_name[name].branch_exists(source_branch)
    ]
    if not policy.allow_uneven_branch_lengths:
        return mirrored
    return [
        (name, destination)
        for name, destination in mirrored
        if len(
            repos_by_name[name].commits_on_branch_and_not_other(
                source_branch, destination
            )
        )
        == len(qualifying_steps)
    ]


def _validate_fully_participating_repos(
    auth_repo,
    source_branch,
    default_branch,
    policy,
    merge_plan,
    repos_by_name,
    qualifying_steps,
) -> None:
    mirrored = _mirrored_repos(
        source_branch, merge_plan, repos_by_name, qualifying_steps, policy
    )
    if not mirrored:
        return

    fully_participating = [repos_by_name[name] for name, _ in mirrored]
    updated_roles = sorted(
        {
            r
            for step in qualifying_steps
            for r in updated_roles_at_commit(auth_repo, step.auth_commit)
        }
    )
    check_capstone_roles = [
        r for r in updated_roles if r not in policy.no_capstone_roles
    ]
    check_branch_id_role_set = set(policy.check_branch_id_roles)
    check_branch_roles = {
        r: r in check_branch_id_role_set for r in check_capstone_roles
    }
    merge_branches = {
        repos_by_name[name]: destination for name, destination in mirrored
    }
    merge_branches[auth_repo] = default_branch
    check_branch_lengths_fun = (
        (lambda *_a, **_k: None) if policy.allow_uneven_branch_lengths else None
    )
    try:
        validate_branch(
            auth_repo,
            fully_participating,
            source_branch,
            merge_branches,
            updated_roles,
            check_capstone_roles,
            check_branch_roles,
            check_branch_lengths_fun=check_branch_lengths_fun,
        )
    except InvalidBranchError as e:
        raise MergeError(f"{source_branch}: validation error: {e}")


def _apply_merge_plan(source_branch, merge_plan, repos_by_name) -> None:
    for name, (destination, declared_commit) in merge_plan.items():
        repo = repos_by_name[name]
        if repo.get_current_branch() == destination:
            repo.checkout_commit(declared_commit)
        if not repo.force_move_branch(destination, declared_commit):
            raise MergeError(f"{source_branch}: could not move {name} to {destination}")
        repo.checkout_branch(destination)
        taf_logger.info(f"Merged {name} to {destination} at {declared_commit}")


def _set_changed_default_branches(
    merge_plan, repos_by_name, old_destinations, git_access_token
) -> None:
    for name, (destination, _) in merge_plan.items():
        if destination == old_destinations[name]:
            continue
        repo = repos_by_name[name]
        try:
            git_provider = get_git_provider(repo, access_token=git_access_token)
            git_provider.set_default_branch(destination)
            taf_logger.warning(f"{destination} set as default branch in {repo.path}")
        except Exception as e:
            taf_logger.error(
                f"Could not update default branch of {repo.path} due to error:\n{e}.\n"
                "Please update default branch manually."
            )


def _merge_one_branch(
    auth_repo: AuthenticationRepository,
    source_branch: str,
    policy: MergePolicy,
    default_branch: str,
    library_dir: Optional[str],
    keystore: Optional[str],
    git_access_token: Optional[str],
) -> Tuple[int, Set[GitRepository]]:
    """Returns the number of auth commits signed (0 if nothing was merged) and
    the set of target repositories whose destination branch moved."""
    auth_repo.checkout_branch(default_branch)
    auth_repo.checkout_branch(source_branch)

    try:
        unmerged_auth_commits = find_unmerged_auth_commits(
            auth_repo, source_branch, default_branch
        )
    except RoleMetadataNotSameError as e:
        taf_logger.error(str(e))
        return 0, set()

    if not unmerged_auth_commits:
        taf_logger.info(f"{source_branch}: all commits already merged")
        return 0, set()

    repos_by_name = _load_non_archived_repos(
        auth_repo, library_dir, unmerged_auth_commits[-1]
    )
    steps = _build_steps(auth_repo, unmerged_auth_commits, repos_by_name)

    last_index = _last_qualifying_step_index(steps, policy.gate)
    if last_index < 0:
        taf_logger.info(f"{source_branch}: no commits ready to merge yet")
        return 0, set()

    qualifying_steps = steps[: last_index + 1]
    final_step = qualifying_steps[-1]
    planned_merge_plan = _plan_merge(repos_by_name, final_step)
    merge_plan = _drop_or_reject_missing_commits(
        source_branch, planned_merge_plan, repos_by_name
    )
    if planned_merge_plan and not merge_plan:
        # Every repo that had new work was not actually ready for it (the
        # update-branch case) - unlike an empty `planned_merge_plan`, which just
        # means all target repos already sit at their declared commit and the
        # auth commit is signed on its own, this is nothing to merge at all.
        taf_logger.info(f"{source_branch}: no target repository ready to merge yet")
        return 0, set()

    old_destinations = {
        name: (
            auth_repo.get_target(name, auth_repo.top_commit_of_branch(default_branch))
            or {}
        ).get("branch")
        or repos_by_name[name].default_branch
        for name in merge_plan
    }

    _validate_fully_participating_repos(
        auth_repo,
        source_branch,
        default_branch,
        policy,
        merge_plan,
        repos_by_name,
        qualifying_steps,
    )
    _apply_merge_plan(source_branch, merge_plan, repos_by_name)

    auth_repo.checkout_branch(default_branch)
    for step in qualifying_steps:
        commit_roles = updated_roles_at_commit(auth_repo, step.auth_commit)
        _sign_and_merge_commit(auth_repo, step.auth_commit, commit_roles, keystore)

    if policy.set_default_branch:
        _set_changed_default_branches(
            merge_plan, repos_by_name, old_destinations, git_access_token
        )

    return len(qualifying_steps), {repos_by_name[name] for name in merge_plan}


def _rename_merged_branch(auth_repo: AuthenticationRepository, branch: str) -> None:
    new_branch_name = f"merged/{branch}"
    try:
        auth_repo._git(f"checkout {branch}")
        auth_repo._git(f"branch -m {new_branch_name}")
        auth_repo._git(f"push origin {new_branch_name} --no-verify")
        auth_repo._git(f"push origin --delete {branch} --no-verify")
        auth_repo._git(
            f"branch --set-upstream-to=origin/{new_branch_name} {new_branch_name}"
        )
        auth_repo._git(f"checkout {auth_repo.default_branch}")
    except GitError as e:
        taf_logger.warning(
            f"Failed to rename merged branch {branch} due to error - {str(e)}"
        )


@log_on_start(INFO, "Merging branch commits", logger=taf_logger)
@log_on_end(INFO, "Finished merging branch commits", logger=taf_logger)
@log_on_error(
    ERROR,
    "An error occurred while merging branch commits: {e}",
    logger=taf_logger,
    on_exceptions=TAFError,
    reraise=True,
)
def merge_branch_commits(
    path: str,
    *,
    policy: MergePolicy,
    pin_manager: Optional[PinManager] = None,
    library_dir: Optional[str] = None,
    pushed_branch: Optional[str] = None,
    keystore: Optional[str] = None,
    deploy: bool = False,
    git_access_token: Optional[str] = None,
) -> MergeResult:
    """
    Merge commits of the branch(es) matching `policy.branch_pattern` - the
    newest overall, or the newest per `policy.group_by` group - into each
    participating target repository's destination branch and the
    authentication repository's default branch.

    Arguments:
        path: Path to the authentication repository.
        policy: The merge policy to apply - see `taf.models.merge.MergePolicy`.
        pin_manager (optional): Reused across calls if the caller already has one (e.g.
            `auth_repo.pin_manager`); a fresh one is created if not given.
        library_dir (optional): Directory containing the target repositories.
        pushed_branch (optional): If given, this call is a no-op unless it matches
            `policy.branch_pattern` (used to filter which CI trigger should act).
        keystore (optional): Location of the keystore files.
        deploy (optional): Push changes (and merged target repositories) to their remotes.
        git_access_token (optional): Access token used to change a target repository's
            default branch, when `policy.set_default_branch` is set.

    Side Effects:
        Force-moves destination branches of participating target repositories, re-signs
        and commits snapshot/timestamp metadata of the authentication repository for each
        merged commit, and (if `deploy`) pushes all of it, optionally renaming merged
        branches.

    Raises:
        MergeError, RoleMetadataNotSameError

    Returns:
        A `MergeResult` describing what was merged - empty if there was nothing to do.
    """
    pattern = BranchPattern(policy.branch_pattern)
    if pushed_branch is not None and not pattern.matches(pushed_branch):
        taf_logger.info(
            f"Pushed branch {pushed_branch} does not match pattern "
            f"'{policy.branch_pattern}', nothing to merge"
        )
        return MergeResult()

    if pin_manager is None:
        pin_manager = PinManager()

    auth_repo = AuthenticationRepository(path=path, pin_manager=pin_manager)
    default_branch = auth_repo.default_branch
    if default_branch is None:
        raise MergeError(f"Could not determine the default branch of {path}")
    auth_repo.checkout_branch(default_branch)
    try:
        validate_from_commit = auth_repo.top_commit_of_branch(default_branch)
    except GitError:
        validate_from_commit = None

    _verify_previously_merged_repos_intact(auth_repo, default_branch, library_dir)

    source_branches = select_branches(auth_repo, pattern, group_by=policy.group_by)
    if not source_branches:
        taf_logger.info(f"No branch matching pattern '{policy.branch_pattern}' found")
        return MergeResult()

    merged_branches: List[str] = []
    touched_repos: Set[GitRepository] = set()
    signed_commits = 0
    for source_branch in source_branches:
        branch_signed_commits, repos = _merge_one_branch(
            auth_repo,
            source_branch,
            policy,
            default_branch,
            library_dir,
            keystore,
            git_access_token,
        )
        if branch_signed_commits:
            merged_branches.append(source_branch)
            signed_commits += branch_signed_commits
            touched_repos.update(repos)

    if not merged_branches:
        return MergeResult()

    try:
        validate_repository(
            path,
            library_dir,
            validate_from_commit=(
                validate_from_commit.hash if validate_from_commit else None
            ),
        )
    except ValidationFailedError as e:
        raise MergeError(f"Could not merge branch commits due to validation error: {e}")
    except Exception as e:
        raise MergeError(
            "An error occurred while validating repositories. This most likely means "
            f"there is a problem with the TAF updater.\n{e}"
        )

    result = MergeResult(
        merged_branches=merged_branches,
        moved_repos=sorted(repo.name for repo in touched_repos),
        signed_commits=signed_commits,
    )

    if not deploy:
        taf_logger.info("deploy=False; skipping push")
        return result

    taf_logger.info(f"Pushing {len(touched_repos)} target repo(s) and auth repo")
    for repo in touched_repos:
        repo.push()
    auth_repo.push()

    if policy.rename_merged:
        for branch in merged_branches:
            _rename_merged_branch(auth_repo, branch)

    return result
