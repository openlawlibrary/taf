import pytest
from taf.exceptions import GitError
from taf.git import GitRepository


def test_commits_on_branch_and_not_other(repository: GitRepository):
    branch_name = "new-branch"
    repository.create_and_checkout_branch(branch_name)
    commit1 = repository.commit_empty("test commit1")
    commit2 = repository.commit_empty("test commit2")
    commit3 = repository.commit_empty("test commit3")
    assert repository.default_branch
    all_commits = repository.commits_on_branch_and_not_other(
        branch_name, repository.default_branch
    )
    assert len(all_commits) == 3
    for commit in (commit1, commit2, commit3):
        assert commit in all_commits


def test_commits_on_branch_and_not_other_when_base_branch_exists_only_on_remote(
    origin_repo: GitRepository,
    clone_repository: GitRepository,
    repository: GitRepository,
):
    # Push a feature branch (created from main) to origin
    default_branch = repository.default_branch
    assert default_branch
    repository.add_remote("origin", str(origin_repo.path))
    feature_branch = "feature"
    repository.create_and_checkout_branch(feature_branch)
    commit1 = repository.commit_empty("feature commit1")
    commit2 = repository.commit_empty("feature commit2")
    repository.push(branch=feature_branch, set_upstream=True)

    # Clone origin - main is checked out locally, feature is remote-only
    clone_repository.urls = [str(origin_repo.path)]
    clone_repository.clone()
    clone_repository.fetch(branch=feature_branch)

    # Simulate the default branch being changed on the remote: delete local main
    # so it only exists as origin/main (remote tracking)
    clone_repository.checkout_branch(feature_branch)
    clone_repository.delete_branch(default_branch)

    assert not clone_repository.branch_exists(default_branch, include_remotes=False)
    assert clone_repository.branch_exists(default_branch)

    # Should return only the 2 feature commits, not all commits on the branch
    commits = clone_repository.commits_on_branch_and_not_other(
        feature_branch, default_branch
    )
    assert len(commits) == 2
    assert set(commits) == {commit1, commit2}


def test_commits_on_branch_and_not_other_raises_when_branch_does_not_exist(
    repository: GitRepository,
):
    branch_name = "new-branch"
    repository.create_and_checkout_branch(branch_name)
    repository.commit_empty("test commit1")
    with pytest.raises(GitError, match="does not exist"):
        repository.commits_on_branch_and_not_other(branch_name, "nonexistent-branch")
