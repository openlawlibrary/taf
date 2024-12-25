from pathlib import Path

from taf.constants import CAPSTONE, METADATA_DIRECTORY_NAME, TARGETS_DIRECTORY_NAME
from taf.exceptions import GitError, InvalidBranchError
from taf.tuf.repository import MetadataRepository, get_target_path


def validate_branch(
    auth_repo,
    target_repos,
    branch_name,
    merge_branches,
    updated_roles,
    check_capstone_roles=None,
    check_branch_roles=None,
    check_branch_lengths_fun=None,
):
    """
    Validates corresponding branches of the authentication repository
    and the target repositories. Assumes that:
    1. Commits of the target repositories' branches are merged into the default (main) branch
    2. Commits of the authentication repository are not merged into the default (main) branch
    directly - fresh timestamp and snapshot are generated.
    Checks if:
    1. For each target repository, a commit sha of each commit of the specified branch matches
    the commit sha stored in the target file corresponding to that repository.
    2. Versions of tuf metadata increase by one from one commit
    to the next commit of a branch in the authentication repository
    3. The last commit of the authentication repository's branch has capstone set (meaning
    that a capstone file is one of the targets specified in targets metadata)
    4. If all commits of an authentication repository's branch have the same branch ID
    """
    if check_branch_roles is None:
        check_branch_roles = {}
    if check_capstone_roles is not None:
        for role in check_capstone_roles:
            check_capstone(auth_repo, branch_name, role)
    targets_and_commits = {
        target_repo: target_repo.commits_on_branch_and_not_other(
            branch_name, merge_branches[target_repo]
        )
        for target_repo in target_repos
    }
    auth_commits = auth_repo.commits_on_branch_and_not_other(
        branch_name, merge_branches[auth_repo]
    )

    if check_branch_lengths_fun:
        check_branch_lengths_fun(targets_and_commits, branch_name)
    else:
        _check_lengths_of_branches(targets_and_commits, branch_name)

    unmodified_roles_and_versions = {
        role_name: None
        for role_name in _get_unchanged_targets_metadata(auth_repo, updated_roles)
    }

    # Get the missing commits from the top of the merge branch
    # and make sure that they belonged to the branch

    for target_repo, commits in targets_and_commits.items():
        num_of_merged_commits = len(auth_commits) - len(commits)
        if num_of_merged_commits:
            commits.extend(
                target_repo.list_n_commits(
                    num_of_merged_commits, branch=merge_branches[target_repo]
                )
            )
    for updated_role in updated_roles:
        branch_id = None
        targets_version = None
        for commit_index, auth_commit in enumerate(auth_commits):
            # load content of the updated role's targets metadata
            updated_targets = auth_repo.get_json(
                auth_commit, f"{METADATA_DIRECTORY_NAME}/{updated_role}.json"
            )
            targets_version = _check_updated_targets_version(
                updated_targets, updated_role, auth_commit, targets_version
            )
            for (
                role_name,
                unmodified_roles_version,
            ) in unmodified_roles_and_versions.items():
                unmodified_target_metadata = auth_repo.get_json(
                    auth_commit, f"{METADATA_DIRECTORY_NAME}/{role_name}.json"
                )
                version = _check_if_version_unmodified(
                    unmodified_target_metadata,
                    role_name,
                    auth_commit,
                    unmodified_roles_version,
                )
                if unmodified_roles_version is None:
                    unmodified_roles_and_versions[role_name] = version

            if updated_role in check_branch_roles:
                no_initial_branch_id = check_branch_roles[updated_role]
                branch_id = _check_branch_id(
                    auth_repo,
                    auth_commit,
                    branch_id,
                    updated_role,
                    is_first_commit=no_initial_branch_id
                    and commit_index == len(auth_commits) - 1,
                )

            for target, target_commits in targets_and_commits.items():
                target_commit = target_commits[commit_index]

                # targets' commits match the target commits specified in the authentication repository
                _compare_commit_with_targets_metadata(
                    auth_repo, auth_commit, target, target_commit
                )


def _check_lengths_of_branches(targets_and_commits, branch_name):
    """
    Checks if branches of the given name have the same number
    of commits in each of the provided repositories.
    """

    lengths = set(len(commits) for commits in targets_and_commits.values())
    if len(lengths) > 1:
        msg = (
            f"Branches {branch_name} of target repositories do not have the"
            " same number of commits"
        )
        for target, commits in targets_and_commits.items():
            msg += f"\n{target.name} has {len(commits)} commits."
        raise InvalidBranchError(msg)


def _check_branch_id(auth_repo, auth_commit, branch_id, role, is_first_commit):

    new_branch_id = None
    for branch_path in (str(Path(role, "branch")), "branch"):
        if auth_repo.get_role_from_target_paths([str(branch_path)]) == role:
            try:
                new_branch_id = auth_repo.get_target(auth_commit, branch_path)
            except GitError:
                pass
            else:
                break
    if (
        (branch_id is not None and new_branch_id is None and not is_first_commit)
        or branch_id is not None
        and new_branch_id != branch_id
    ):
        raise InvalidBranchError(
            f"Branch ID at revision {auth_commit} is not the same as the "
            "version at the following revision"
        )
    return new_branch_id


def _check_updated_targets_version(targets, role_name, auth_commit, current_version):
    """
    Checks version numbers specified in target role's metadata file (compares it to the previous one)
    There are no other metadata files to check. Expects the version to be eual to
    current_version - 1. Returns the read version number.
    """
    new_version = targets["signed"]["version"]
    # substracting one because the commits are in the reverse order
    if current_version is not None and new_version != current_version - 1:
        raise InvalidBranchError(
            f"Version of metadata file {role_name}.json at revision "
            f"{auth_commit} is not equal to previous version incremented "
            "by one!"
        )
    return new_version


def _check_if_version_unmodified(targets, role_name, auth_commit, current_version):
    """
    Checks version numbers specified in target role's metadata file.json
    (compares it to the previous one). Expects the version number to be the same
    as current_version (if current_version is not None). Returns the version
    """
    new_version = targets["signed"]["version"]
    # substracting one because the commits are in the reverse order
    if current_version is not None and new_version != current_version:
        raise InvalidBranchError(
            f"Version of metadata file {role_name}.json at revision "
            f"{auth_commit} is not equal to previous version!"
        )
    return new_version


def check_capstone(auth_repo, branch, role):
    """
    Check if there is a capstone file (a target file called capstone)
    at the end of the specified branch.
    """

    auth_commit = auth_repo.top_commit_of_branch(branch)
    found = False

    for capstone_path in (str(Path(role, CAPSTONE).as_posix()), CAPSTONE):
        if auth_repo.get_role_from_target_paths([capstone_path]) == role:
            try:
                target_path = get_target_path(capstone_path)
                auth_repo.get_file(auth_commit, target_path)
                found = True
            except GitError:
                pass
            else:
                break
    if not found:
        raise InvalidBranchError(
            f"No capstone at the end of branch {branch} for role {role}!!!"
        )


def _compare_commit_with_targets_metadata(
    tuf_repo, tuf_commit, target_repo, target_repo_commit
):
    """
    Check if commit sha of a repository's speculative branch commit matches the
    specified target value in its target file.
    """
    repo_name = f"{TARGETS_DIRECTORY_NAME}/{target_repo.name}"
    try:
        targets_head_sha = tuf_repo.get_json(tuf_commit, repo_name)["commit"]
    except GitError:
        if target_repo_commit is not None:
            raise InvalidBranchError(
                f"Target file {repo_name} does not exist in revision {tuf_commit}"
            )
        targets_head_sha = None

    if target_repo_commit != targets_head_sha:
        raise InvalidBranchError(
            f"Commit {target_repo_commit} of repository {target_repo.name} does "
            "not match the commit sha specified in its target file!"
        )


def _get_unchanged_targets_metadata(auth_repo, updated_roles):
    taf_repo = MetadataRepository(auth_repo.path)
    all_roles = taf_repo.get_all_targets_roles()
    all_roles = [*(set(all_roles) - set(updated_roles))]
    return all_roles
