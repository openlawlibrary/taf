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


def _check_no_force_push(source_branch, merge_plan, repos_by_name) -> None:
    for name, (_, declared_commit) in merge_plan.items():
        repo = repos_by_name[name]
        if not repo.branches_containing_commit(declared_commit):
            raise MergeError(
                f"{source_branch}: declared commit {declared_commit} for {name} no "
                "longer exists on any branch of that repository - check for a force push"
            )


def _validate_fully_participating_repos(
    auth_repo,
    source_branch,
    default_branch,
    policy,
    merge_plan,
    repos_by_name,
    qualifying_steps,
) -> None:
    fully_participating = [
        repos_by_name[name]
        for name, (destination, _) in merge_plan.items()
        if repos_by_name[name].branch_exists(source_branch)
        and len(
            repos_by_name[name].commits_on_branch_and_not_other(
                source_branch, destination
            )
        )
        == len(qualifying_steps)
    ]
    if not fully_participating:
        return

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
    merge_branches = {repo: merge_plan[repo.name][0] for repo in fully_participating}
    merge_branches[auth_repo] = default_branch
    try:
        validate_branch(
            auth_repo,
            fully_participating,
            source_branch,
            merge_branches,
            updated_roles,
            check_capstone_roles,
            check_branch_roles,
            check_branch_lengths_fun=lambda *_a, **_k: None,
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
) -> Tuple[bool, Set]:
    auth_repo.checkout_branch(default_branch)
    auth_repo.checkout_branch(source_branch)

    try:
        unmerged_auth_commits = find_unmerged_auth_commits(
            auth_repo, source_branch, default_branch
        )
    except RoleMetadataNotSameError as e:
        taf_logger.error(str(e))
        return False, set()

    if not unmerged_auth_commits:
        taf_logger.info(f"{source_branch}: all commits already merged")
        return False, set()

    repos_by_name = _load_non_archived_repos(
        auth_repo, library_dir, unmerged_auth_commits[-1]
    )
    steps = _build_steps(auth_repo, unmerged_auth_commits, repos_by_name)

    last_index = _last_qualifying_step_index(steps, policy.gate)
    if last_index < 0:
        taf_logger.info(f"{source_branch}: no commits ready to merge yet")
        return False, set()

    qualifying_steps = steps[: last_index + 1]
    final_step = qualifying_steps[-1]
    merge_plan = _plan_merge(repos_by_name, final_step)

    old_destinations = {
        name: (
            auth_repo.get_target(name, auth_repo.top_commit_of_branch(default_branch))
            or {}
        ).get("branch")
        or repos_by_name[name].default_branch
        for name in merge_plan
    }

    _check_no_force_push(source_branch, merge_plan, repos_by_name)
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

    return True, {repos_by_name[name] for name in merge_plan}


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
    pin_manager: PinManager,
    policy: MergePolicy,
    library_dir: Optional[str] = None,
    pushed_branch: Optional[str] = None,
    keystore: Optional[str] = None,
    deploy: bool = False,
    git_access_token: Optional[str] = None,
) -> None:
    """
    Merge commits of the branch(es) matching `policy.branch_pattern` - the
    newest overall, or the newest per `policy.group_by` group - into each
    participating target repository's destination branch and the
    authentication repository's default branch.

    Arguments:
        path: Path to the authentication repository.
        policy: The merge policy to apply - see `taf.models.merge.MergePolicy`.
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
        None
    """
    pattern = BranchPattern(policy.branch_pattern)
    if pushed_branch is not None and not pattern.matches(pushed_branch):
        taf_logger.info(
            f"Pushed branch {pushed_branch} does not match pattern "
            f"'{policy.branch_pattern}', nothing to merge"
        )
        return

    auth_repo = AuthenticationRepository(path=path, pin_manager=pin_manager)
    default_branch = auth_repo.default_branch
    if default_branch is None:
        raise MergeError(f"Could not determine the default branch of {path}")
    auth_repo.checkout_branch(default_branch)
    try:
        validate_from_commit = auth_repo.top_commit_of_branch(default_branch)
    except GitError:
        validate_from_commit = None

    source_branches = select_branches(auth_repo, pattern, group_by=policy.group_by)
    if not source_branches:
        taf_logger.info(f"No branch matching pattern '{policy.branch_pattern}' found")
        return

    merged_branches = []
    touched_repos: Set = set()
    for source_branch in source_branches:
        signed, repos = _merge_one_branch(
            auth_repo,
            source_branch,
            policy,
            default_branch,
            library_dir,
            keystore,
            git_access_token,
        )
        if signed:
            merged_branches.append(source_branch)
            touched_repos.update(repos)

    if not merged_branches:
        return

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

    if not deploy:
        taf_logger.info("deploy=False; skipping push")
        return

    taf_logger.info(f"Pushing {len(touched_repos)} target repo(s) and auth repo")
    for repo in touched_repos:
        repo.push()
    auth_repo.push()

    if policy.rename_merged:
        for branch in merged_branches:
            _rename_merged_branch(auth_repo, branch)
