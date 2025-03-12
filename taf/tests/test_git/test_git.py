import datetime
import json
from pygit2 import AlreadyExistsError
from taf.models.types import Commitish
import pytest
import tempfile
from taf.exceptions import GitError, NothingToCommitError
from taf.git import GitRepository


def test_initial_commit(repository):
    commit = repository.initial_commit
    assert type(commit) == Commitish
    assert commit.hash
    assert commit.value


def test_get_head_commit_sha(repository):
    commit = repository.head_commit()
    assert type(commit) == Commitish
    assert commit.hash
    assert commit.value


def test_head_commit_sha_when_no_repo():
    with tempfile.TemporaryDirectory() as tmpdirname:
        repo = GitRepository(path=tmpdirname)
        with pytest.raises(
            GitError,
            match=f"Repo {repo.name}: The path '{repo.path.as_posix()}' is not a Git repository.",
        ):
            repo.head_commit() is not None


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


def test_commit_on_branch_an_not_other(repository: GitRepository):
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


def test_remotes(origin_repo: GitRepository, clone_repository: GitRepository):
    clone_repository.urls = [str(origin_repo.path)]
    clone_repository.clone()
    assert clone_repository.remotes == ["origin"]


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


def test_fetch_from_local(repository: GitRepository, clone_repository: GitRepository):
    clone_repository.clone_from_disk(repository.path)
    branch1 = "branch1"
    branch2 = "branch2"
    repository.create_branch(branch1)
    repository.create_branch(branch2)
    clone_repository.fetch_from_disk(repository.path, [branch1, branch2])
    branches = clone_repository.branches(all=True)
    assert branch1 in branches and branch2 in branches


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
