from taf.git import GitRepository
from taf.tests.test_git.conftest import TEST_DIR, CLONE_REPO_NAME


def test_clone_from_local(repository, clone_repository):
    clone_repository.clone_from_disk(repository.path)
    assert clone_repository.is_git_repository
    commits = clone_repository.all_commits_on_branch()
    assert len(commits)
