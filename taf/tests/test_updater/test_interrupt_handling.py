import os
import signal
import pytest
from pathlib import Path

from taf.exceptions import UpdateFailedError
from taf.updater.updater import update_repository
from taf.updater.updater import UpdateConfig
from taf.updater.types.update import OperationType
from taf.git import GitRepository


class DummyRepo:
    """Fake empty git repo used for path presence."""
    def __init__(self, path):
        self.path = path
        self.name = "dummy"
        self.is_git_repository = True
        self.is_bare_repository = False

    def get_remote_url(self):
        return "https://example.com/repo.git"


@pytest.fixture
def fake_repo(tmp_path, monkeypatch):
    """Create a tmp directory and mock GitRepository so no actual git commands run."""
    repo_path = tmp_path / "auth"
    repo_path.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr("taf.updater.updater.GitRepository", lambda path: DummyRepo(path))

    return repo_path


def test_update_repository_interrupts_gracefully(fake_repo, monkeypatch):
    """
    Simulate Ctrl+C (SIGINT) during update_repository and ensure UpdateFailedError is raised.
    """

    config = UpdateConfig(
        path=fake_repo,
        operation=OperationType.UPDATE,
        remote_url="https://example.com/repo.git",
        strict=True,
        run_scripts=False,
    )

    def fake_update(*args, **kwargs):
        # Immediately simulate Ctrl+C by sending SIGINT to the current process
        os.kill(os.getpid(), signal.SIGINT)

    monkeypatch.setattr("taf.updater.updater._update_or_clone_repository", fake_update)

    with pytest.raises(UpdateFailedError, match="interrupted"):
        update_repository(config)
