"""Fixtures and scenario setup for the Git LFS tests.

Git LFS keeps a small text *pointer* in the repository and the real bytes in a
separate store, moved by the ``smudge`` and ``clean`` filters git runs on
checkout and commit. Those filters are configured in git config, and a clone
inherits global and system config but not the source repository's local config,
so ``lfs_global_config`` makes them visible globally for the duration of a test.
"""

from functools import partial
from pathlib import Path
from typing import List, Optional

import pytest
from loguru import logger

from taf.git import GitRepository
from taf.tests.test_updater.conftest import SetupManager, add_valid_target_commits
from taf.tests.test_updater.test_lfs.lfs_server import LFSServer
from taf.tests.test_updater.update_utils import load_target_repositories
from taf.utils import run

#: Pattern committed to ``.gitattributes`` so git routes these files to LFS.
LFS_TRACKED_PATTERN = "*.bin"
LFS_FILE_NAME = "large_file.bin"

#: An ordinary, non-LFS file, for checking the filter stays out of the way.
PLAIN_FILE_NAME = "plain_file.txt"

LFS_POINTER_PREFIX = b"version https://git-lfs.github.com/spec/v1"


def assert_lfs_content_materialized(repo_path: Path, revision: str) -> None:
    """Assert the working tree holds real LFS content, not a pointer.

    The three failure modes are separated because they have different causes: a
    missing file means the checkout never happened, a pointer means the smudge
    filter did not run, and wrong bytes mean the wrong revision.
    """
    file_path = repo_path / LFS_FILE_NAME
    assert file_path.is_file(), f"{file_path} was never checked out"

    content = file_path.read_bytes()
    expected = lfs_file_content(revision)

    assert not is_lfs_pointer(content), (
        f"{file_path} contains a Git LFS pointer instead of the file's content, "
        f"so the smudge filter did not run for this checkout.\n"
        f"pointer:\n{content[:200].decode(errors='replace')}"
    )
    assert content == expected, (
        f"{file_path} holds unexpected bytes: expected the {revision} payload "
        f"({len(expected)} bytes), found {len(content)} bytes starting with "
        f"{content[:40]!r}"
    )


def build_lfs_origin(path: Path, other_branch: str = "other") -> GitRepository:
    """Create a standalone LFS origin with two revisions on separate branches.

    The default branch ends at the ``v2`` payload and ``other_branch`` pins
    ``v1``, so a checkout between them has to rewrite the tracked file.
    """
    repo = _init_repo(path)
    write_lfs_file(repo, "v1")
    repo.commit("Add LFS-tracked file (v1)")
    repo.create_branch(other_branch)
    write_lfs_file(repo, "v2")
    repo.commit("Update LFS-tracked file (v2)")
    return repo


def build_plain_origin(path: Path, other_branch: str = "other") -> GitRepository:
    """Like ``build_lfs_origin``, with no LFS involved."""
    repo = _init_repo(path)
    (path / PLAIN_FILE_NAME).write_text("plain v1")
    repo.commit("Add plain file (v1)")
    repo.create_branch(other_branch)
    (path / PLAIN_FILE_NAME).write_text("plain v2")
    repo.commit("Update plain file (v2)")
    return repo


def commit_lfs_content(origin_auth_repo, revision: str, lfs_url: Optional[str] = None):
    """Commit LFS-tracked content to every target repository and sign.

    Verifies that the committed blob really is a pointer, so a test can never
    pass against content that silently bypassed LFS.
    """
    setup_manager = SetupManager(origin_auth_repo)
    setup_manager.add_task(
        add_valid_target_commits,
        {
            "mutate": partial(write_lfs_file, revision=revision, lfs_url=lfs_url),
            "commit_message": f"Update LFS-tracked file ({revision})",
        },
    )
    setup_manager.execute_tasks()

    for target_repo in load_target_repositories(origin_auth_repo).values():
        head_commit = target_repo.head_commit()
        blob = target_repo.get_file(head_commit, LFS_FILE_NAME)
        assert LFS_POINTER_PREFIX.decode() in blob, (
            f"{target_repo.name}: {LFS_FILE_NAME} was committed as a normal blob, "
            "so this test is not exercising Git LFS"
        )


def enable_lfs(repo: GitRepository, lfs_url: Optional[str] = None) -> None:
    """Install the LFS filters into ``repo`` and track the LFS pattern there.

    When ``lfs_url`` is given, write a ``.lfsconfig`` pinning the LFS endpoint.
    ``.lfsconfig`` is committed, so it travels with the repository through
    clones and lets a client resolve objects from the LFS server rather than
    from whichever git remote it was cloned from.
    """
    run("git", "-C", str(repo.path), "lfs", "install", "--local")
    run("git", "-C", str(repo.path), "lfs", "track", LFS_TRACKED_PATTERN)
    if lfs_url is not None:
        (repo.path / ".lfsconfig").write_text(f"[lfs]\n\turl = {lfs_url}\n")


def git_lfs_version() -> str:
    """The installed ``git lfs`` version, or "" when unavailable.

    Checks the subcommand rather than the binary: a ``git-lfs`` on PATH that git
    cannot dispatch to is useless here.
    """
    from taf.lfs import get_git_lfs_executable

    if get_git_lfs_executable() is None:
        return ""
    try:
        return run("git", "lfs", "version") or ""
    except Exception:
        return ""


def is_lfs_pointer(content: bytes) -> bool:
    """True if ``content`` is an unsmudged LFS pointer instead of real data."""
    return content.startswith(LFS_POINTER_PREFIX)


def lfs_file_content(revision: str) -> bytes:
    """Deterministic, recognizable payload for the LFS-tracked file.

    Padded well past a pointer file's length, and distinct per revision so a
    stale checkout is distinguishable from a missing smudge.
    """
    return f"LFS-CONTENT-{revision}-".encode() + revision.encode() * 512


@pytest.fixture(autouse=True)
def lfs_global_config(monkeypatch, tmp_path, deterministic_git_environment):
    """Make the LFS filters visible to git globally, for this test only.

    Extends the suite's generated config with what ``git lfs install`` writes,
    rather than running that command and editing the developer's real
    ``~/.gitconfig``.
    """
    config_path = tmp_path / "lfs_gitconfig"
    config_path.write_text(
        "\n".join(
            [
                "[include]",
                f"\tpath = {Path(deterministic_git_environment).as_posix()}",
                '[filter "lfs"]',
                "\tclean = git-lfs clean -- %f",
                "\tsmudge = git-lfs smudge -- %f",
                "\tprocess = git-lfs filter-process",
                "\trequired = true",
            ]
        )
        + "\n"
    )
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(config_path))
    return config_path


@pytest.fixture
def lfs_log():
    """Collect what ``taf.lfs`` logs during a test.

    TAF logs through loguru, so pytest's ``caplog`` sees nothing. pygit2
    discards the exception raised inside a filter, which makes the log the only
    place the reason survives.
    """
    messages: List[str] = []
    handler_id = logger.add(
        lambda message: messages.append(message.record["message"]),
        level="WARNING",
        filter=lambda record: record["name"] == "taf.lfs",
        format="{message}",
    )
    yield messages
    logger.remove(handler_id)


@pytest.fixture
def lfs_server(tmp_path):
    """A real Git LFS endpoint on 127.0.0.1 for the duration of one test."""
    with LFSServer(tmp_path / "lfs-storage") as server:
        yield server


def publish_lfs_objects(origin_auth_repo, lfs_server) -> None:
    """Move every target repository's LFS objects onto the server.

    Deletes the local copies, so the server is the only possible source and a
    materialized working tree proves an HTTP fetch happened.
    """
    for target_repo in load_target_repositories(origin_auth_repo).values():
        lfs_server.take_local_objects(target_repo.path)


def write_lfs_file(
    target_repo: GitRepository, revision: str, lfs_url: Optional[str] = None
) -> None:
    """Enable LFS in ``target_repo`` and write the tracked file for ``revision``."""
    enable_lfs(target_repo, lfs_url=lfs_url)
    (target_repo.path / LFS_FILE_NAME).write_bytes(lfs_file_content(revision))


def _init_repo(path: Path) -> GitRepository:
    # GitRepository.init_repo() only mkdirs when the directory already exists
    path.mkdir(parents=True, exist_ok=True)
    repo = GitRepository(path=path)
    repo.init_repo()
    return repo
