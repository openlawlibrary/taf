import pytest
import tempfile
from taf.exceptions import GitError
from taf.git import GitRepository


def test_clone_from_local(repository, clone_repository):
    clone_repository.clone_from_disk(repository.path)
    assert clone_repository.is_git_repository
    commits = clone_repository.all_commits_on_branch()
    assert len(commits)


def test_branch_unpushed_commits(repository, clone_repository):
    clone_repository.clone_from_disk(repository.path, keep_remote=True)
    branch = clone_repository.branches()[0]
    clone_repository.reset_num_of_commits(1, True)
    has_unpushed, unpushed_commits = clone_repository.branch_unpushed_commits(branch)
    assert not has_unpushed
    assert not len(unpushed_commits)
    (clone_repository.path / "test3.txt").write_text("Updated test3")
    clone_repository.commit(message="Update test3.txt")
    has_unpushed, unpushed_commits = clone_repository.branch_unpushed_commits(branch)
    assert has_unpushed
    assert len(unpushed_commits)


def test_is_git_repository_root_bare(repository):
    repository.init_repo(bare=True)
    assert repository.is_git_repository
    assert repository.is_git_repository_root


def test_is_git_repository_root_non_bare(repository):
    repository.init_repo(bare=False)
    assert repository.is_git_repository
    assert repository.is_git_repository_root


def test_head_commit_sha():
    with tempfile.TemporaryDirectory() as tmpdirname:
        repo = GitRepository(path=tmpdirname)
        with pytest.raises(
            GitError,
            match=f"Repo {repo.name}: The path '{repo.path.as_posix()}' is not a Git repository.",
        ):
            repo.head_commit_sha() is not None


def test_all_commits_since_commit_when_repo_empty(empty_repository):
    all_commits_empty = empty_repository.all_commits_since_commit()
    assert isinstance(all_commits_empty, list)
    assert len(all_commits_empty) == 0


def test_get_last_remote_commit(origin_repo, clone_repository):
    clone_repository.urls = [origin_repo.path]
    clone_repository.clone()
    clone_repository.commit_empty("test commit1")
    top_commit = clone_repository.commit_empty("test commit2")
    clone_repository.push()
    initial_commit = clone_repository.initial_commit
    clone_repository.reset_to_commit(initial_commit)
    assert (
        clone_repository.top_commit_of_branch(clone_repository.default_branch)
        == initial_commit
    )
    last_remote_on_origin = clone_repository.get_last_remote_commit(
        clone_repository.get_remote_url()
    )
    assert last_remote_on_origin == top_commit


def test_reset_to_commit_when_reset_remote_tracking(origin_repo, clone_repository):
    # reset to commit is also expected to update the remote tracking branch by default
    clone_repository.urls = [origin_repo.path]
    clone_repository.clone()
    initial_commit = clone_repository.initial_commit
    clone_repository.reset_to_commit(initial_commit)
    assert (
        clone_repository.top_commit_of_remote_branch(clone_repository.default_branch)
        == initial_commit
    )


def test_reset_to_commit_when_not_reset_remote_tracking(origin_repo, clone_repository):
    # reset to commit is also expected to update the remote tracking branch by default
    clone_repository.urls = [origin_repo.path]
    clone_repository.clone()
    top_commit = clone_repository.head_commit_sha()
    initial_commit = clone_repository.initial_commit
    clone_repository.reset_to_commit(initial_commit, reset_remote_tracking=False)
    assert (
        clone_repository.top_commit_of_remote_branch(clone_repository.default_branch)
        == top_commit
    )
