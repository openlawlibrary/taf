import datetime
import json
import os
from pathlib import Path
from typing import List
from pygit2 import AlreadyExistsError
from taf.models.types import Commitish
import pytest
import tempfile
import time
from taf.exceptions import (
    GitAccessDeniedException,
    GitError,
    NoRemoteError,
    NothingToCommitError,
    PygitError,
    UpdateFailedError,
)
import taf.git as git_module
from taf.git import GitRepository
from taf.tests.test_git.conftest import (
    push_commit_then_reset,
    push_new_branch,
)
from taf.tests.utils import nested_git_repository


def test_initial_commit(repository):
    commit = repository.initial_commit
    assert type(commit) == Commitish
    assert commit.hash
    assert commit.value


def test_is_commit_an_ancestor_of_a_commit_or_branch(repository: GitRepository):
    parent = repository.commit_empty("parent commit")
    head = repository.commit_empty("head commit")
    branch = repository.get_current_branch()

    assert repository.is_commit_an_ancestor_of_a_commit_or_branch(parent, head.hash)
    assert repository.is_commit_an_ancestor_of_a_commit_or_branch(parent, branch)
    assert repository.is_commit_an_ancestor_of_a_commit_or_branch(head, head.hash)
    assert not repository.is_commit_an_ancestor_of_a_commit_or_branch(head, parent.hash)


def test_get_head_commit_sha(repository):
    commit = repository.head_commit()
    assert type(commit) == Commitish
    assert commit.hash
    assert commit.value


def test_get_last_branch_by_committer_date(repository: GitRepository):
    default_branch = repository.get_current_branch()
    time.sleep(1.1)
    repository.checkout_branch("aaa-latest", create=True)
    repository.commit_empty("commit made after the default branch's last commit")
    repository.checkout_branch(default_branch)

    last_branch = repository.get_last_branch_by_committer_date()

    assert last_branch is not None
    assert last_branch.strip() == "aaa-latest"


def test_head_commit_sha_when_no_repo():
    with tempfile.TemporaryDirectory() as tmpdirname:
        repo = GitRepository(path=tmpdirname)
        with pytest.raises(
            GitError,
            match=f"Repo {repo.name}: The path '{repo.path.as_posix()}' is not a Git repository.",
        ):
            repo.head_commit() is not None


def test_pygit_requires_pygit2(monkeypatch, repository):
    monkeypatch.setattr(git_module, "PYGIT2_AVAILABLE", False)
    repo = GitRepository(path=repository.path, default_branch=repository.default_branch)

    with pytest.raises(PygitError, match="pygit2 is not installed"):
        _ = repo.pygit


def test_remote_exists(repository: GitRepository, origin_repo: GitRepository):
    assert not repository.remote_exists("origin")

    repository.add_remote("origin", str(origin_repo.path))

    assert repository.remote_exists("origin")
    assert not repository.remote_exists("upstream")


def test_clone(origin_repo: GitRepository, clone_repository: GitRepository):
    clone_repository.urls = [str(origin_repo.path)]
    clone_repository.clone()
    assert clone_repository.is_git_repository


def test_create_branch(repository: GitRepository):
    head_commit = repository.head_commit()
    assert head_commit
    branch_name = "new-branch"
    repository.create_branch(branch_name)
    assert repository.branch_exists(branch_name)
    with pytest.raises(AlreadyExistsError):
        repository.create_branch(branch_name)


def test_commit(repository: GitRepository):
    commits_num = len(repository.all_commits_on_branch())
    msg = "test message"
    with pytest.raises(NothingToCommitError):
        repository.commit(msg)
    (repository.path / "test_file").touch()
    commit = repository.commit(msg)
    assert len(repository.all_commits_on_branch()) == commits_num + 1
    assert repository.get_commit_message(commit).strip() == msg


def test_commit_empty(repository: GitRepository):
    commits_num = len(repository.all_commits_on_branch())
    msg = "test message"
    commit = repository.commit_empty(msg)
    assert len(repository.all_commits_on_branch()) == commits_num + 1
    assert repository.get_commit_message(commit).strip() == msg


def test_create_and_checkout_branch(repository: GitRepository):
    head_commit = repository.head_commit()
    assert head_commit
    branch_name = "new-branch"
    repository.create_and_checkout_branch(branch_name)
    assert repository.branch_exists(branch_name)
    all_commits_on_branch = repository.all_commits_on_branch(branch_name)
    assert head_commit in all_commits_on_branch
    assert repository.get_current_branch() == branch_name


def test_clone_from_local(repository: GitRepository, clone_repository: GitRepository):
    clone_repository.clone_from_disk(repository.path)
    assert clone_repository.is_git_repository
    commits = clone_repository.all_commits_on_branch()
    assert len(commits)


def test_clone_or_pull_clones_when_repository_does_not_exist(
    origin_repo: GitRepository, clone_repository: GitRepository
):
    clone_repository.urls = [str(origin_repo.path)]

    old_head, new_head = clone_repository.clone_or_pull()

    assert old_head is None
    assert new_head == origin_repo.head_commit()


def test_clone_or_pull_only_fetch_updates_the_given_local_branch(
    cloned_repository: GitRepository,
):
    behind_commit = cloned_repository.head_commit()
    assert behind_commit is not None
    pushed_commit = push_new_branch(cloned_repository, "feature", with_commit=True)
    cloned_repository.force_move_branch("feature", behind_commit.hash)
    assert cloned_repository.top_commit_of_branch("feature") == behind_commit

    cloned_repository.clone_or_pull(branches=["feature"], only_fetch=True)

    assert cloned_repository.top_commit_of_branch("feature") == pushed_commit


def test_clone_or_pull_pulls_new_commits(cloned_repository: GitRepository):
    pushed_commit = push_commit_then_reset(cloned_repository)

    old_head, new_head = cloned_repository.clone_or_pull()

    assert old_head != pushed_commit
    assert new_head == pushed_commit


def test_clone_from_disk_requires_pygit2(monkeypatch, tmp_path):
    monkeypatch.setattr(git_module, "PYGIT2_AVAILABLE", False)
    repo = GitRepository(path=tmp_path / "clone", default_branch="main")

    with pytest.raises(PygitError, match="pygit2 is not installed"):
        repo.clone_from_disk(tmp_path / "source")


def test_branches(repository: GitRepository):
    assert repository.branches() == [repository.default_branch]
    branch1 = "branch1"
    branch2 = "branch2"
    repository.create_branch(branch1)
    assert set(repository.branches()) == {repository.default_branch, branch1}
    repository.create_branch(branch2)
    assert set(repository.branches()) == {repository.default_branch, branch1, branch2}


def test_branch_exists(repository: GitRepository):
    assert repository.default_branch
    assert repository.branch_exists(repository.default_branch)
    branch1 = "branch1"
    assert not repository.branch_exists(branch1)
    repository.create_branch(branch1)
    assert repository.branch_exists(branch1)


def test_branch_off_commit(repository: GitRepository):
    commit1 = repository.commit_empty("commit 1")
    commit2 = repository.commit_empty("commit 2")
    assert repository.head_commit() == commit2
    branch_name = "new_branch"
    repository.branch_off_commit(branch_name, commit1)
    assert repository.top_commit_of_branch(branch_name) == commit1


def test_branch_local_name(origin_repo: GitRepository, clone_repository: GitRepository):
    clone_repository.urls = [str(origin_repo.path)]
    clone_repository.clone()
    remote = clone_repository.remotes[0]
    assert clone_repository.branch_local_name(f"{remote}/test") == "test"


def test_branch_unpushed_commits(
    repository: GitRepository, clone_repository: GitRepository
):
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


def test_is_git_repository_root_bare(repository: GitRepository):
    repository.init_repo(bare=True)
    assert repository.is_git_repository
    assert repository.is_git_repository_root


def test_is_git_repository_root_non_bare(repository: GitRepository):
    repository.init_repo(bare=False)
    assert repository.is_git_repository
    assert repository.is_git_repository_root


def test_is_git_repository_root_linked_worktree(repository: GitRepository, tmp_path):
    """A linked worktree is a repository root, though its git directory lives
    under the repository it belongs to."""
    worktree_path = Path(tmp_path) / "worktree"
    repository._git("worktree add {} -b wtbranch", str(worktree_path))

    worktree = GitRepository(path=worktree_path)

    assert worktree.is_git_repository_root
    assert worktree.default_branch == "wtbranch"


def test_is_git_repository_root_submodule(repository: GitRepository, tmp_path):
    """A submodule is a repository root, though its git directory lives under
    the superproject."""
    submodule_source = Path(tmp_path) / "submodule_source"
    submodule_source.mkdir()
    source = GitRepository(path=submodule_source)
    source.init_repo()
    (submodule_source / "sub.txt").write_text("Some example text")
    source.commit(message="Add sub.txt")
    source.rename_branch(source.get_current_branch(), "subbranch")
    repository._git(
        "-c protocol.file.allow=always submodule add {} sub", str(submodule_source)
    )

    submodule = GitRepository(path=repository.path / "sub")

    assert submodule.is_git_repository_root
    assert submodule.default_branch == "subbranch"
    assert repository.default_branch != "subbranch"


def test_is_path_ignored(repository: GitRepository):
    (repository.path / ".gitignore").write_text("*.log\nbuild/\n")

    assert repository.is_path_ignored("debug.log")
    assert repository.is_path_ignored("build/output.txt")
    assert not repository.is_path_ignored("test1.txt")


def test_is_git_repository_root_git_directory(repository: GitRepository):
    """The git directory is not the root; the work tree is."""
    assert not GitRepository(path=repository.path / ".git").is_git_repository_root


def test_is_git_repository_root_malformed_git_file(tmp_path):
    """A `.git` file that is not a gitdir pointer is not a repository.

    An interrupted write leaves one behind, and `repository_utils` asks this
    of every ancestor of a path, so raising here would break unrelated work.
    """
    path = Path(tmp_path) / "malformed"
    path.mkdir()
    (path / ".git").write_text("not a gitdir pointer")

    assert GitRepository(path=path).is_git_repository_root is False


def test_clone_clears_state_read_from_the_enclosing_repository(
    origin_repo: GitRepository, clone_repository: GitRepository
):
    """The fixture path sits inside this checkout, so reading through pygit2
    before the clone resolves to it."""
    clone_repository.urls = [str(origin_repo.path)]
    assert clone_repository.head_commit() != origin_repo.head_commit()

    clone_repository.clone()

    assert clone_repository.head_commit() == origin_repo.head_commit()


def test_clone_bare_from_local_clears_state_read_from_the_enclosing_repository(
    repository: GitRepository, clone_repository: GitRepository
):
    """`is_bare_repository` is cached too, and the enclosing repository is not bare."""
    assert clone_repository.head_commit() != repository.head_commit()
    assert not clone_repository.is_bare_repository

    clone_repository.clone_bare_from_local(repository.path)

    assert clone_repository.is_bare_repository
    assert clone_repository.head_commit() == repository.head_commit()


def test_is_git_repository_root_not_cached_negative(repository: GitRepository):
    """is_git_repository_root must not settle on a negative answer: a path
    inside a repository that later becomes a repository itself has to report
    True, rather than the answer from before it existed."""
    nested = nested_git_repository(repository.path)
    assert nested.is_git_repository_root is False

    GitRepository(path=nested.path).init_repo()

    assert nested.is_git_repository_root is True


def test_init_repo_clears_state_read_from_the_enclosing_repository(
    repository: GitRepository,
):
    """Reading through pygit2 before the repository exists resolves to the
    enclosing one; init_repo must not leave that behind."""
    nested = nested_git_repository(repository.path)
    assert nested.head_commit() == repository.head_commit()

    nested.init_repo()

    assert nested.head_commit() is None


def test_clone_from_disk_clears_state_read_from_the_enclosing_repository(
    repository: GitRepository, clone_repository: GitRepository
):
    """The fixture path sits inside this checkout, so reading through pygit2
    before the clone resolves to it."""
    assert clone_repository.head_commit() != repository.head_commit()

    clone_repository.clone_from_disk(repository.path, keep_remote=False)

    assert clone_repository.head_commit() == repository.head_commit()


def test_init_repo_clears_remotes_read_from_the_enclosing_repository(
    repository: GitRepository, tmp_path
):
    """`remotes` is read through pygit2 and cached, so it needs clearing too."""
    repository._git("remote add origin {}", str(tmp_path))
    nested = nested_git_repository(repository.path)
    assert nested.remotes == ["origin"]

    nested.init_repo()

    assert nested.remotes == []


def test_is_git_repository_not_cached_negative(tmp_path):
    """is_git_repository must not permanently cache a negative result: an
    instance created for a path before the repository exists (e.g. before the
    updater or an external process materializes it) has to report True once a
    valid repository appears on disk."""
    repo_path = Path(tmp_path) / "repo"
    repo = GitRepository(path=repo_path)
    # path does not exist yet
    assert repo.is_git_repository is False
    # an external actor creates the repository at that path
    repo_path.mkdir(parents=True, exist_ok=True)
    GitRepository(path=repo_path).init_repo(bare=False)
    # the original instance must now detect it instead of returning a stale False
    assert repo.is_git_repository is True


def test_set_head_to_branch(repository: GitRepository):
    branch_name = "feature"
    repository.create_branch(branch_name)
    repository.set_head_to_branch(branch_name)
    assert repository.get_current_branch() == branch_name


def test_set_tracking_branch(cloned_repository: GitRepository):
    push_new_branch(cloned_repository, "feature")
    assert cloned_repository.get_tracking_branch("feature") is None

    assert cloned_repository.set_tracking_branch("feature") == "origin/feature"

    assert cloned_repository.get_tracking_branch("feature") == "origin/feature"
    assert cloned_repository.set_tracking_branch("feature", strip_remote=True) == (
        "feature"
    )


def test_set_tracking_branch_creates_missing_branch_and_fails_without_remote_branch(
    cloned_repository: GitRepository,
):
    assert not cloned_repository.branch_exists("brand-new")

    assert cloned_repository.set_tracking_branch("brand-new") is None

    assert cloned_repository.branch_exists("brand-new")
    assert cloned_repository.get_tracking_branch("brand-new") is None


def test_set_upstream(cloned_repository: GitRepository):
    push_new_branch(cloned_repository, "feature")
    assert cloned_repository.get_tracking_branch("feature") is None

    cloned_repository.set_upstream("feature")

    assert cloned_repository.get_tracking_branch("feature") == "origin/feature"


def test_set_upstream_does_nothing_when_remote_branch_does_not_exist(
    cloned_repository: GitRepository,
):
    cloned_repository.create_branch("local-only")

    cloned_repository.set_upstream("local-only")

    assert cloned_repository.get_tracking_branch("local-only") is None


def test_synced_with_remote(cloned_repository: GitRepository):
    assert cloned_repository.synced_with_remote()

    cloned_repository.commit_empty("unpushed commit")
    assert not cloned_repository.synced_with_remote()

    cloned_repository.push()
    assert cloned_repository.synced_with_remote()


def test_synced_with_remote_for_specific_branch(cloned_repository: GitRepository):
    push_new_branch(cloned_repository, "feature")
    cloned_repository.set_upstream("feature")
    assert cloned_repository.synced_with_remote(branch="feature")

    cloned_repository.checkout_branch("feature")
    cloned_repository.commit_empty("unpushed commit on feature")
    assert not cloned_repository.synced_with_remote(branch="feature")


def test_synced_with_remote_raises_when_there_is_no_remote(
    repository: GitRepository,
):
    with pytest.raises(NoRemoteError):
        repository.synced_with_remote()


def test_synced_with_remote_when_branch_has_no_tracking_branch(
    cloned_repository: GitRepository,
):
    cloned_repository.create_branch("local-only")

    assert not cloned_repository.synced_with_remote(branch="local-only")


def test_fetch_heads_to_remote_tracking(repository: GitRepository):
    default_branch = repository.default_branch
    assert default_branch is not None
    # no remote-tracking ref before mirroring
    assert not repository.branch_exists(
        f"origin/{default_branch}", include_remotes=True
    )
    repository.fetch_heads_to_remote_tracking()
    # refs/heads/* are now mirrored into refs/remotes/origin/*
    assert repository.top_commit_of_remote_branch(default_branch) == (
        repository.top_commit_of_branch(default_branch)
    )


def test_all_commits_since_commit_when_repo_empty(empty_repository: GitRepository):
    all_commits_empty = empty_repository.all_commits_since_commit()
    assert isinstance(all_commits_empty, list)
    assert len(all_commits_empty) == 0


def test_get_last_remote_commit(
    origin_repo: GitRepository, clone_repository: GitRepository
):
    clone_repository.urls = [str(origin_repo.path)]
    clone_repository.clone()
    clone_repository.commit_empty("test commit1")
    top_commit = clone_repository.commit_empty("test commit2")
    clone_repository.push()
    initial_commit = clone_repository.initial_commit
    clone_repository.reset_to_commit(initial_commit)
    assert clone_repository.default_branch
    assert (
        clone_repository.top_commit_of_branch(clone_repository.default_branch)
        == initial_commit
    )
    last_remote_on_origin = clone_repository.get_last_remote_commit(
        clone_repository.get_remote_url()
    )
    assert last_remote_on_origin == top_commit


def test_reset_to_commit_when_reset_remote_tracking(
    origin_repo: GitRepository, clone_repository: GitRepository
):
    # reset to commit is also expected to update the remote tracking branch by default
    clone_repository.urls = [str(origin_repo.path)]
    clone_repository.clone()
    initial_commit = clone_repository.initial_commit
    clone_repository.reset_to_commit(initial_commit)
    assert (
        clone_repository.top_commit_of_remote_branch(clone_repository.default_branch)
        == initial_commit
    )


def test_resolve_commit(repository: GitRepository):
    parent = repository.commit_empty("parent commit")
    head = repository.commit_empty("head commit")

    assert repository.resolve_commit(head) is head
    assert repository.resolve_commit(head.hash) == head
    assert repository.resolve_commit("HEAD") == head
    assert repository.resolve_commit(repository.get_current_branch()) == head
    assert repository.resolve_commit("HEAD~1") == parent
    assert repository.resolve_commit(head.hash[:10]) == head


def test_resolve_commit_returns_none_for_unknown_revision(repository: GitRepository):
    assert repository.resolve_commit("no-such-revision") is None
    assert repository.resolve_commit("0" * 40) is None


def test_restore_removes_files_and_directories_unknown_to_git(
    repository: GitRepository,
):
    new_file = repository.path / "new.txt"
    new_dir = repository.path / "new_dir"
    new_file.write_text("new")
    new_dir.mkdir()
    (new_dir / "inner.txt").write_text("inner")

    repository.restore([str(new_file), str(new_dir)])

    assert not new_file.exists()
    assert not new_dir.exists()


def test_restore_restores_deleted_file(repository: GitRepository):
    (repository.path / "test1.txt").unlink()

    repository.restore(["test1.txt"])

    assert (repository.path / "test1.txt").read_text() == "Some example text 1"


def test_restore_reverts_modified_and_staged_files(repository: GitRepository):
    (repository.path / "test1.txt").write_text("modified in working tree")
    (repository.path / "test2.txt").write_text("modified and staged")
    repository._git("add {}", "test2.txt")

    repository.restore(["test1.txt", "test2.txt"])

    assert (repository.path / "test1.txt").read_text() == "Some example text 1"
    assert (repository.path / "test2.txt").read_text() == "Some example text 2"
    assert not repository.something_to_commit()


def test_restore_with_no_paths_does_nothing(repository: GitRepository):
    (repository.path / "test1.txt").write_text("modified")

    repository.restore([])

    assert (repository.path / "test1.txt").read_text() == "modified"


def test_reset_to_commit_when_not_reset_remote_tracking(
    origin_repo: GitRepository, clone_repository: GitRepository
):
    clone_repository.urls = [str(origin_repo.path)]
    clone_repository.clone()
    assert clone_repository.default_branch
    top_commit = clone_repository.head_commit()
    initial_commit = clone_repository.initial_commit
    clone_repository.reset_to_commit(initial_commit, reset_remote_tracking=False)
    assert (
        clone_repository.top_commit_of_remote_branch(clone_repository.default_branch)
        == top_commit
    )


def test_detached_head(repository: GitRepository):
    assert not repository.is_detached_head
    assert repository.initial_commit
    repository.checkout_commit(repository.initial_commit)
    assert repository.is_detached_head


def test_all_commits_on_branch(repository: GitRepository):
    initial_commit = repository.initial_commit
    commit1 = repository.commit_empty("test commit1")
    commit2 = repository.commit_empty("test commit2")
    commit3 = repository.commit_empty("test commit3")
    all_commits = repository.all_commits_on_branch()
    for commit in (initial_commit, commit1, commit2, commit3):
        assert commit in all_commits
    all_commits[-1] == commit3
    all_commits[0] == initial_commit
    all_commits_revered = repository.all_commits_on_branch(reverse=True)
    for commit in (initial_commit, commit1, commit2, commit3):
        assert commit in all_commits_revered
    all_commits[-1] == initial_commit
    all_commits[0] == commit3

    branch_name = "new-branch"
    repository.create_and_checkout_branch(branch_name)
    commit4 = repository.commit_empty("test commit4")
    commit5 = repository.commit_empty("test commit5")
    commit6 = repository.commit_empty("test commit")
    all_commits_on_new_branch = repository.all_commits_on_branch(branch=branch_name)
    for commit in (
        initial_commit,
        commit1,
        commit2,
        commit3,
        commit4,
        commit5,
        commit6,
    ):
        assert commit in all_commits_on_new_branch


def test_all_commits_since_commit(repository: GitRepository):
    commit1 = repository.commit_empty("test commit1")
    commit2 = repository.commit_empty("test commit2")
    commit3 = repository.commit_empty("test commit3")
    all_commits_since_commit = repository.all_commits_since_commit(commit1)
    assert len(all_commits_since_commit) == 2
    assert all_commits_since_commit == [commit2, commit3]
    all_commits_since_commit_reverse = repository.all_commits_since_commit(
        commit1, reverse=False
    )
    assert len(all_commits_since_commit_reverse) == 2
    assert all_commits_since_commit_reverse == [commit3, commit2]


def test_branches_containing_commit(repository: GitRepository):
    commit1 = repository.commit_empty("test commit1")
    branches = repository.branches_containing_commit(commit1)
    branches == [repository.default_branch]
    branch = "new-branch"
    repository.create_branch(branch)
    branches = repository.branches_containing_commit(commit1)
    branches == [repository.default_branch, branch]


def test_checkout_commit(repository: GitRepository):
    commit1 = repository.commit_empty("test commit1")
    repository.commit_empty("test commit2")
    repository.checkout_commit(commit1)
    assert repository.head_commit() == commit1


def test_commit_exists(repository: GitRepository):
    commit1 = repository.commit_empty("test commit1")
    assert repository.commit_exists(commit1)
    assert not repository.commit_exists(Commitish.from_hash("123456"))


def test_commit_before_commit(repository: GitRepository):
    commit1 = repository.commit_empty("test commit1")
    commit2 = repository.commit_empty("test commit2")
    commit3 = repository.commit_empty("test commit3")
    assert repository.commit_before_commit(commit3) == commit2
    assert repository.commit_before_commit(commit2) == commit1


def test_get_commit_date(repository: GitRepository):
    commit1 = repository.commit_empty("test commit1")
    assert repository.get_commit_date(commit1) == str(datetime.date.today())


def test_get_first_commit_on_branch(repository: GitRepository):
    repository.commit_empty("test commit1")
    assert (
        repository.get_first_commit_on_branch(repository.default_branch)
        == repository.initial_commit
    )
    branch = "new-branch"
    repository.create_branch(branch)
    assert repository.get_first_commit_on_branch(branch) == repository.initial_commit


def test_list_files_at_revision(repository: GitRepository):
    test1 = "test_file1"
    test2 = "test_file2"
    dir_path = repository.path / "test"
    dir_path.mkdir()
    (dir_path / test1).touch()
    (dir_path / test2).touch()
    commit = repository.commit("test commit")
    files_at_revision = repository.list_files_at_revision(commit, "test")
    assert set(files_at_revision) == {test1, test2}


def test_list_modified_files(repository: GitRepository):
    (repository.path / "test1.txt").write_text("changed")
    (repository.path / "test2.txt").unlink()
    (repository.path / "untracked.txt").write_text("untracked")

    assert repository.list_modified_files() == ["test1.txt", "test2.txt"]
    assert repository.list_modified_files(with_status=True) == [
        ("M", "test1.txt"),
        ("D", "test2.txt"),
    ]
    assert repository.list_modified_files(path="test1.txt") == ["test1.txt"]


def test_list_modified_files_when_nothing_is_modified(repository: GitRepository):
    assert repository.list_modified_files() == []


def test_list_changed_files_at_revision(repository: GitRepository):
    test1 = "test_file1"
    test2 = "test_file2"
    dir_path = repository.path / "test"
    dir_path.mkdir()
    (dir_path / test1).touch()
    (dir_path / test2).touch()
    commit = repository.commit("test commit")
    files_at_revision = repository.list_changed_files_at_revision(commit)
    assert set(files_at_revision) == {f"test/{test1}", f"test/{test2}"}


def test_list_commits(repository: GitRepository):
    initial_commit = repository.initial_commit
    commit1 = repository.commit_empty("test commit1")
    commit2 = repository.commit_empty("test commit2")
    commit3 = repository.commit_empty("test commit3")
    all_commits = repository.list_commits()
    for commit in (initial_commit, commit1, commit2, commit3):
        assert commit in all_commits


def test_list_n_commits(repository: GitRepository):
    repository.commit_empty("test commit1")
    commit2 = repository.commit_empty("test commit2")
    commit3 = repository.commit_empty("test commit3")
    all_commits = repository.list_n_commits(number=2)
    for commit in (commit2, commit3):
        assert commit in all_commits


def test_list_tags(repository: GitRepository):
    assert repository.list_tags() == []

    repository._git("tag {}", "v1.0")
    repository._git("tag {}", "v2.0")

    assert repository.list_tags() == ["v1.0", "v2.0"]


def test_list_untracked_files(repository: GitRepository):
    assert repository.list_untracked_files() == []
    (repository.path / "untracked1.txt").write_text("a")
    (repository.path / "dir").mkdir()
    (repository.path / "dir" / "untracked2.txt").write_text("b")

    assert sorted(repository.list_untracked_files()) == [
        "dir/untracked2.txt",
        "untracked1.txt",
    ]
    assert repository.list_untracked_files("dir") == ["dir/untracked2.txt"]

    repository.commit("Add untracked files")

    assert repository.list_untracked_files() == []


def test_merge_branch_allow_new_commit_creates_merge_commit(
    repository: GitRepository,
):
    default_branch = repository.get_current_branch()
    repository.checkout_branch("feature", create=True)
    (repository.path / "feature.txt").write_text("feature")
    repository.commit("Add feature.txt")
    repository.checkout_branch(default_branch)
    (repository.path / "main.txt").write_text("main")
    repository.commit("Add main.txt")

    repository.merge_branch("feature", allow_new_commit=True)

    head = repository.pygit_repo.revparse_single("HEAD")
    assert len(head.parents) == 2
    assert (repository.path / "feature.txt").is_file()
    assert (repository.path / "main.txt").is_file()
    assert not repository.something_to_commit()


def test_merge_branch_fast_forward(repository: GitRepository):
    default_branch = repository.get_current_branch()
    repository.checkout_branch("feature", create=True)
    feature_commit = repository.commit_empty("feature commit")
    repository.checkout_branch(default_branch)
    assert repository.head_commit() != feature_commit

    repository.merge_branch("feature")

    assert repository.head_commit() == feature_commit


def test_merge_commit(repository: GitRepository):
    branch = "new-branch"
    repository.create_branch(branch)
    num_of_commits = len(repository.all_commits_on_branch(branch))
    commit1 = repository.commit_empty("test commit1")
    repository.merge_commit(commit1, branch)
    assert len(repository.all_commits_on_branch(branch)) == num_of_commits + 1


def test_reset_to_commit(repository: GitRepository):
    commit1 = repository.commit_empty("test commit1")
    commit2 = repository.commit_empty("test commit2")
    assert repository.head_commit() == commit2
    repository.reset_to_commit(commit1)
    assert repository.head_commit() == commit1


def test_safely_get_json(repository: GitRepository):
    test_file = "test.json"
    (repository.path / test_file).write_text(json.dumps({"test1": "test1"}))
    commit1 = repository.commit("test")
    (repository.path / test_file).write_text(json.dumps({"test2": "test2"}))
    commit2 = repository.commit("test")
    file1 = repository.safely_get_json(commit1, test_file)
    assert file1
    assert "test1" in file1
    file2 = repository.safely_get_json(commit2, test_file)
    assert file2
    assert "test2" in file2


def test_top_commit_of_branch(repository: GitRepository):
    branch = "new-branch"
    repository.create_and_checkout_branch(branch)
    commit1 = repository.commit_empty("test commit1")
    assert repository.top_commit_of_branch(branch) == commit1
    commit2 = repository.commit_empty("test commit2")
    assert repository.top_commit_of_branch(branch) == commit2


def test_update_branch_refs(repository: GitRepository):
    parent = repository.commit_empty("parent commit")
    repository.commit_empty("head commit")
    repository.create_branch("feature")

    repository.update_branch_refs("feature", parent)

    assert repository.top_commit_of_branch("feature") == parent
    assert repository.top_commit_of_branch("origin/feature") == parent


def test_update_local_branch(cloned_repository: GitRepository):
    default_branch = cloned_repository.get_current_branch()
    pushed_commit = push_commit_then_reset(cloned_repository)
    assert cloned_repository.top_commit_of_branch(default_branch) != pushed_commit

    cloned_repository.update_local_branch(default_branch)

    assert cloned_repository.top_commit_of_branch(default_branch) == pushed_commit


def test_update_ref_for_bare_repository(origin_repo: GitRepository):
    branch = origin_repo.get_current_branch()
    head = origin_repo.head_commit()
    assert head is not None
    parent = origin_repo.commit_before_commit(head)
    assert parent is not None

    origin_repo.update_ref_for_bare_repository(branch, parent)

    assert origin_repo.top_commit_of_branch(branch) == parent


def test_update_ref_for_bare_repository_raises_for_unknown_commit(
    origin_repo: GitRepository,
):
    with pytest.raises(UpdateFailedError):
        origin_repo.update_ref_for_bare_repository(
            origin_repo.get_current_branch(), Commitish.from_hash("1" * 40)
        )


def test_remotes(origin_repo: GitRepository, clone_repository: GitRepository):
    clone_repository.urls = [str(origin_repo.path)]
    clone_repository.clone()
    assert clone_repository.remotes == ["origin"]


def test_remove_remote(cloned_repository: GitRepository):
    assert cloned_repository.has_remote()

    cloned_repository.remove_remote("origin")

    assert not cloned_repository.remote_exists("origin")
    assert not cloned_repository.has_remote()


def test_remove_remote_that_does_not_exist_does_not_raise(
    cloned_repository: GitRepository,
):

    cloned_repository.remove_remote("upstream")

    assert cloned_repository.remote_exists("origin")


def test_reset_remote_tracking_branch(cloned_repository: GitRepository):
    default_branch = cloned_repository.get_current_branch()
    local_commit = cloned_repository.commit_empty("local only")
    assert cloned_repository.top_commit_of_branch(f"origin/{default_branch}") != (
        local_commit
    )

    cloned_repository.reset_remote_tracking_branch(default_branch)

    assert cloned_repository.top_commit_of_branch(f"origin/{default_branch}") == (
        local_commit
    )


def test_add_remote(origin_repo: GitRepository, clone_repository: GitRepository):
    clone_repository.urls = [str(origin_repo.path)]
    clone_repository.clone()
    assert clone_repository.remotes == ["origin"]
    clone_repository.add_remote("origin2", "https://test.com")
    assert clone_repository.remotes == ["origin", "origin2"]


def test_checkout_branch(repository: GitRepository):
    assert repository.get_current_branch() == repository.default_branch
    branch = "new-branch"
    repository.create_branch(branch)
    assert repository.get_current_branch() == repository.default_branch
    repository.checkout_branch(branch)
    repository.get_current_branch() == branch


def test_if_clean_and_synced_when_dirty_index(
    origin_repo: GitRepository, clone_repository: GitRepository
):
    clone_repository.urls = [str(origin_repo.path)]
    clone_repository.clone()
    assert clone_repository.check_if_clean_and_synced()
    (clone_repository.path / "test").touch()
    assert not clone_repository.check_if_clean_and_synced()


def test_if_clean_and_synced_when_additional_commit(
    origin_repo: GitRepository, clone_repository: GitRepository
):
    clone_repository.urls = [str(origin_repo.path)]
    clone_repository.clone()
    assert clone_repository.check_if_clean_and_synced()
    clone_repository.commit_empty("test")
    assert not clone_repository.check_if_clean_and_synced()


def test_if_clean_and_synced_when_remote_commit(
    origin_repo: GitRepository, clone_repository: GitRepository
):
    clone_repository.urls = [str(origin_repo.path)]
    clone_repository.clone()
    assert clone_repository.check_if_clean_and_synced()
    clone_repository.commit_empty("test")
    assert not clone_repository.check_if_clean_and_synced()
    clone_repository.push()
    assert clone_repository.check_if_clean_and_synced()
    clone_repository.reset_num_of_commits(1)
    assert not clone_repository.check_if_clean_and_synced()


def test_checkout_paths(repository: GitRepository):
    head_commit = repository.head_commit()
    assert head_commit
    updated_file = repository.path / "test1.txt"
    old_text = updated_file.read_text()
    new_text = "some updated text"
    updated_file.write_text(new_text)
    assert repository.get_file(head_commit, "test1.txt") == old_text
    repository.checkout_paths(head_commit, "test1.txt")
    assert updated_file.read_text() == old_text


def test_checkout_orphan_branch(repository: GitRepository):
    head_commit = repository.head_commit()
    assert head_commit
    branch_name = "new-orphan-branch"
    repository.checkout_orphan_branch(branch_name)
    repository.commit_empty("test")
    repository.commit_empty("test")
    assert repository.branch_exists(branch_name)
    all_commits_on_orphan = repository.all_commits_on_branch(branch_name)
    assert head_commit not in all_commits_on_orphan


def test_check_files_exist(repository: GitRepository):
    existing_expected = {"test1.txt", "test2.txt"}
    missing_expected = {"test5.txt"}
    existing_actual, missing_actual = repository.check_files_exist(
        ["test1.txt", "test2.txt", "test5.txt"]
    )
    assert existing_expected == set(existing_actual)
    assert missing_expected == set(missing_actual)


def test_clean(repository: GitRepository):
    assert not repository.something_to_commit()
    (repository.path / "test").touch()
    assert repository.something_to_commit()
    repository.clean()
    assert not repository.something_to_commit()


def test_clean_and_reset(repository: GitRepository):
    assert not repository.something_to_commit()
    (repository.path / "test").touch()
    updated_file = repository.path / "test1.txt"
    old_text = updated_file.read_text()
    new_text = "some updated text"
    updated_file.write_text(new_text)
    assert repository.something_to_commit()
    repository.clean_and_reset()
    assert not repository.something_to_commit()
    assert updated_file.read_text() == old_text


def test_clean_and_reset_repo_with_no_commits(empty_repository):
    # a repo with staged/untracked changes but no commits at all yet -
    # `git reset --hard HEAD` fails on it since there's no HEAD commit to
    # reset to, so clean_and_reset must still succeed
    repo = empty_repository
    (repo.path / "untracked.txt").touch()
    staged_file = repo.path / "staged.txt"
    staged_file.write_text("staged content")
    repo._git("add staged.txt")
    assert repo.something_to_commit()

    repo.clean_and_reset()

    assert not repo.something_to_commit()
    assert not staged_file.exists()


def test_clear_default_branch(repository: GitRepository):
    repository.default_branch = repository._determine_default_branch()
    assert repository.default_branch is not None
    assert str(repository.path) in git_module._default_branch_cache

    repository.clear_default_branch()

    assert repository.default_branch is None
    assert str(repository.path) not in git_module._default_branch_cache


def test_create_local_branch_from_remote_tracking(
    origin_repo: GitRepository, clone_repository: GitRepository
):
    branch_name = "new_branch"
    origin_repo.create_branch(branch_name)
    clone_repository.urls = [str(origin_repo.path)]
    clone_repository.clone()
    assert clone_repository.is_git_repository
    local_branches = clone_repository.branches(remote=False)
    assert branch_name not in local_branches
    clone_repository.create_local_branch_from_remote_tracking(branch_name)
    local_branches = clone_repository.branches(remote=False)
    assert branch_name in local_branches


def test_delete_local_branch(repository: GitRepository):
    branch_name = "new_branch"
    repository.create_branch(branch_name)
    branch_name in repository.branches(remote=False)
    repository.delete_branch(branch_name)
    branch_name not in repository.branches(remote=False)


def test_delete_remote_branch(
    origin_repo: GitRepository, cloned_repository: GitRepository
):
    push_new_branch(cloned_repository, "feature")
    assert origin_repo.branch_exists("feature")

    cloned_repository.delete_remote_branch("feature")

    assert not origin_repo.branch_exists("feature")


def test_delete_remote_branch_with_explicit_remote_and_no_verify(
    origin_repo: GitRepository, cloned_repository: GitRepository
):
    push_new_branch(cloned_repository, "feature")

    cloned_repository.delete_remote_branch("feature", remote="origin", no_verify=True)

    assert not origin_repo.branch_exists("feature")


def test_delete_remote_tracking_branch(cloned_repository: GitRepository):
    push_new_branch(cloned_repository, "feature")
    assert "origin/feature" in cloned_repository.branches(all=True)

    cloned_repository.delete_remote_tracking_branch("origin/feature")

    assert "origin/feature" not in cloned_repository.branches(all=True)


def test_delete_remote_tracking_branch_force_deletes_unmerged_branch(
    cloned_repository: GitRepository,
):
    push_new_branch(cloned_repository, "feature", with_commit=True)

    cloned_repository.delete_remote_tracking_branch("origin/feature", force=True)

    assert "origin/feature" not in cloned_repository.branches(all=True)


def test_diff_between_revisions(repository: GitRepository):
    head_commit = repository.head_commit()
    assert head_commit
    (repository.path / "test_file").touch()
    (repository.path / "test1.txt").write_text("updated text")
    (repository.path / "test2.txt").unlink()
    commit = repository.commit("test")
    assert commit
    diff = repository.diff_between_revisions(head_commit.value, commit.value)
    modified_files = []
    deleted_files = []
    added_files = []

    # Split the diff output into lines and process each line
    for line in diff.split("\n"):
        if line.startswith("M"):
            modified_files.append(line[2:])
        elif line.startswith("D"):
            deleted_files.append(line[2:])
        elif line.startswith("A"):
            added_files.append(line[2:])

    # Expected lists
    expected_modified = ["test1.txt"]
    expected_deleted = ["test2.txt"]
    expected_added = ["test_file"]
    assert modified_files == expected_modified
    assert deleted_files == expected_deleted
    assert added_files == expected_added


def test_has_remote(origin_repo: GitRepository, clone_repository: GitRepository):
    clone_repository.urls = [str(origin_repo.path)]
    clone_repository.clone()
    assert clone_repository.has_remote()


def test_find_first_branch_matching_pattern(repository: GitRepository):
    def _pattern_func(branch_name):
        return branch_name.startswith("test/")

    def _pattern_func_no_match(branch_name):
        return branch_name.startswith("doesntexist")

    repository.create_branch("test/branch1")
    repository.commit_empty("test1")
    repository.create_branch("test/branch2")
    repository.commit_empty("test2")
    repository.create_branch("test3")
    default_branch = repository.default_branch
    assert default_branch
    branch = repository.find_first_branch_matching_pattern(
        default_branch, _pattern_func
    )
    assert branch == "test/branch2"
    branch = repository.find_first_branch_matching_pattern(
        default_branch, _pattern_func_no_match
    )
    assert branch is None


def test_force_move_branch(repository: GitRepository):
    parent = repository.commit_empty("parent commit")
    head = repository.commit_empty("head commit")
    repository.create_branch("moved")
    assert repository.top_commit_of_branch("moved") == head

    assert repository.force_move_branch("moved", parent.hash)

    assert repository.top_commit_of_branch("moved") == parent


def test_force_move_branch_returns_false_for_unknown_commit(
    repository: GitRepository,
):
    repository.create_branch("moved")
    head = repository.head_commit()

    assert not repository.force_move_branch("moved", "0" * 40)

    assert repository.top_commit_of_branch("moved") == head


def test_get_branch_reference_falls_back_to_remote_tracking_branch(
    cloned_repository: GitRepository,
):
    push_new_branch(cloned_repository, "feature")
    cloned_repository.delete_local_branch("feature")

    assert cloned_repository.get_branch_reference("feature") == "origin/feature"


def test_get_branch_reference_raises_when_branch_does_not_exist(
    repository: GitRepository,
):
    with pytest.raises(GitError):
        repository.get_branch_reference("missing-branch")


def test_get_branch_reference_returns_local_branch_name(repository: GitRepository):
    default_branch = repository.get_current_branch()
    assert repository.get_branch_reference(default_branch) == default_branch


def test_fetch(origin_repo: GitRepository, clone_repository: GitRepository):
    clone_repository.urls = [str(origin_repo.path)]
    clone_repository.clone()
    branch1 = "branch1"
    branch2 = "branch2"
    origin_repo.create_branch(branch1)
    origin_repo.create_branch(branch2)
    clone_repository.fetch()
    branches = clone_repository.branches(all=True)
    assert branch1 not in branches and branch2 not in branches
    assert f"origin/{branch1}" in branches and f"origin/{branch2}" in branches


def test_fetch_retries_on_failure_then_succeeds(
    origin_repo: GitRepository,
    cloned_repository: GitRepository,
    tmp_path: Path,
    monkeypatch,
):
    origin_repo.create_branch("feature")
    moved_origin = tmp_path / "moved_origin"
    origin_repo.path.rename(moved_origin)
    sleeps: List[float] = []

    def put_origin_back_on_second_retry(seconds):
        sleeps.append(seconds)
        if len(sleeps) == 2:
            moved_origin.rename(origin_repo.path)

    monkeypatch.setattr(git_module.time, "sleep", put_origin_back_on_second_retry)

    cloned_repository.fetch()

    assert sleeps == [1, 2]
    assert "origin/feature" in cloned_repository.branches(all=True)


def test_fetch_raises_after_exhausting_retries(
    origin_repo: GitRepository,
    cloned_repository: GitRepository,
    tmp_path: Path,
    monkeypatch,
):
    moved_origin = tmp_path / "moved_origin"
    origin_repo.path.rename(moved_origin)
    sleeps: List[float] = []
    monkeypatch.setattr(git_module.time, "sleep", sleeps.append)

    with pytest.raises(GitAccessDeniedException):
        cloned_repository.fetch()

    moved_origin.rename(origin_repo.path)
    assert sleeps == [1, 2, 4, 8, 16]


def test_fetch_from_local(repository: GitRepository, clone_repository: GitRepository):
    clone_repository.clone_from_disk(repository.path)
    branch1 = "branch1"
    branch2 = "branch2"
    repository.create_branch(branch1)
    repository.create_branch(branch2)
    clone_repository.fetch_from_disk(repository.path, [branch1, branch2])
    branches = clone_repository.branches(all=True)
    assert branch1 in branches and branch2 in branches


def test_fetch_heads_from_remote(
    repository: GitRepository, clone_repository: GitRepository
):
    clone_repository.clone_bare_from_local(repository.path)
    default_branch = repository.get_current_branch()
    seeded_commit = clone_repository.top_commit_of_branch(default_branch)
    new_commit = repository.commit_empty("commit after the seed")
    assert seeded_commit != new_commit

    clone_repository.fetch_heads_from_remote()

    assert clone_repository.top_commit_of_branch(default_branch) == new_commit


def test_get_merge_base(repository: GitRepository):
    branch = "new-branch"
    head_commit = repository.head_commit()
    assert head_commit
    repository.create_and_checkout_branch(branch)
    repository.commit_empty("test 1")
    repository.commit_empty("test 2")
    default_branch = repository.default_branch
    assert default_branch
    assert head_commit == repository.get_merge_base(default_branch, branch)


def test_get_tracking_branch(
    origin_repo: GitRepository, clone_repository: GitRepository
):
    clone_repository.urls = [str(origin_repo.path)]
    clone_repository.clone()
    default_branch = clone_repository.default_branch
    assert (
        clone_repository.get_tracking_branch(default_branch)
        == f"origin/{default_branch}"
    )
    assert (
        clone_repository.get_tracking_branch(default_branch, strip_remote=True)
        == default_branch
    )


def test_is_remote_branch(origin_repo: GitRepository, clone_repository: GitRepository):
    clone_repository.urls = [str(origin_repo.path)]
    clone_repository.clone()
    assert clone_repository.is_remote_branch(
        f"origin/{clone_repository.default_branch}"
    )
    assert not clone_repository.is_remote_branch(
        f"origin2/{clone_repository.default_branch}"
    )


def test_is_git_repository_in_subdirectory(repository: GitRepository):
    # parity with `rev-parse --is-inside-work-tree`: a path inside a work tree
    # is reported as a git repository (discover_repository searches upward)
    subdir = repository.path / "nested"
    subdir.mkdir()
    repo = GitRepository(path=subdir, default_branch=repository.default_branch)
    assert repo.is_git_repository


def test_is_git_repository_non_repo():
    with tempfile.TemporaryDirectory() as tmp:
        repo = GitRepository(path=tmp)
        assert not repo.is_git_repository
        assert not repo.is_git_repository_root


def test_default_branch_from_origin_head(
    origin_repo: GitRepository, clone_repository: GitRepository
):
    clone_repository.urls = [str(origin_repo.path)]
    clone_repository.clone()
    # cloned repos have refs/remotes/origin/HEAD; detection reads it in-process
    assert (
        clone_repository._get_default_branch_from_local() == origin_repo.default_branch
    )


def test_default_branch_from_head_no_remote(repository: GitRepository):
    # no origin remote: falls back to local HEAD shorthand
    assert repository._get_default_branch_from_local() == repository.default_branch


def test_is_git_repository_cached_until_clone(repository, tmp_path):
    # before cloning the path is not a repo; the negative result must not be
    # cached past the clone (cloning makes it a repo). tmp_path is outside any
    # git checkout so the pre-clone state is genuinely "not a repository".
    dest = GitRepository(path=tmp_path / "dest")
    dest.path.mkdir()
    assert not dest.is_git_repository
    dest.clone_from_disk(repository.path)
    assert dest.is_git_repository


def test_clone_from_disk_bare_has_origin(repository: GitRepository, tmp_path):
    # `git clone --bare` creates no origin; clone_from_disk must add it for parity
    bare = GitRepository(path=tmp_path / "bare")
    bare.clone_from_disk(
        repository.path, "https://example.com/x.git", is_bare=True, fetch_remote=False
    )
    assert bare.is_bare_repository
    assert bare.get_remote_url() == "https://example.com/x.git"


def test_clone_from_disk_bare_source_populates_origin_refs(
    origin_repo: GitRepository, tmp_path
):
    # materialization hot path: bare source, fetch_remote=False must populate
    # refs/remotes/origin/* from the source's refs/heads/*
    origin_repo.pygit_repo  # ensure instantiated
    user = GitRepository(path=tmp_path / "user")
    user.clone_from_disk(
        origin_repo.path,
        "https://example.com/x.git",
        is_bare=False,
        fetch_remote=False,
    )
    assert not user.is_bare_repository
    default_branch = origin_repo.default_branch
    assert default_branch
    origin_refs = [
        str(r) for r in user.pygit_repo.references if "refs/remotes/origin/" in str(r)
    ]
    assert any(default_branch in ref for ref in origin_refs), origin_refs


@pytest.mark.skipif(
    not hasattr(os, "getuid"), reason="hardlink nlink check is POSIX-only"
)
def test_clone_from_disk_hardlinks_objects(repository: GitRepository, tmp_path):
    # git clone --local hardlinks objects on the same volume
    dest = GitRepository(path=tmp_path / "linked")
    dest.clone_from_disk(repository.path, keep_remote=True)

    def loose_objects(base):
        objects = Path(base) / ".git" / "objects"
        if not objects.exists():
            objects = Path(base) / "objects"
        return [f for d in objects.glob("??") for f in d.iterdir() if f.is_file()]

    dest_objs = loose_objects(dest.path)
    assert dest_objs, "expected loose objects in the clone"
    # at least one object is hardlinked (st_nlink > 1) to the source copy
    assert any(os.stat(obj).st_nlink > 1 for obj in dest_objs)
