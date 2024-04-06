def test_clone_from_local(repository, clone_repository):
    clone_repository.clone_from_disk(repository.path)
    assert clone_repository.is_git_repository
    commits = clone_repository.all_commits_on_branch()
    assert len(commits)


def test_is_branch_with_unpushed_commits(repository, clone_repository):
    clone_repository.clone_from_disk(repository.path, keep_remote=True)
    branch = clone_repository.branches()[0]
    clone_repository.reset_num_of_commits(1, True)
    assert not clone_repository.is_branch_with_unpushed_commits(branch)
    (clone_repository.path / "test3.txt").write_text("Updated test3")
    clone_repository.commit(message="Update test3.txt")
    assert clone_repository.is_branch_with_unpushed_commits(branch)
