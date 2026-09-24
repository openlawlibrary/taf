"""Fixtures and scenario setup for the Git LFS tests.

Git LFS keeps a small text *pointer* in the repository and the real bytes in a
separate store, moved by the ``smudge`` and ``clean`` filters git runs on
checkout and commit. Those filters are configured in git config, and a clone
inherits global and system config but not the source repository's local config,
so ``lfs_global_config`` makes them visible globally for the duration of a test.
"""

import shutil
import subprocess
from pathlib import Path
from typing import Callable, Optional

import pytest

from taf.git import GitRepository
from taf.utils import run

#: Pattern committed to ``.gitattributes`` so git routes these files to LFS.
LFS_TRACKED_PATTERN = "*.bin"
LFS_FILE_NAME = "large_file.bin"


#: Skips what needs the binary; used by every module in this package.
needs_git_lfs = pytest.mark.skipif(
    not shutil.which("git-lfs"), reason="git-lfs is not installed"
)


def assert_committed_as_lfs_pointer(repo: GitRepository, file_name: str) -> None:
    """Assert ``file_name`` is stored in ``repo``'s HEAD commit as an LFS pointer.

    A misconfigured ``.gitattributes`` would commit the payload as an ordinary
    blob, exercising no LFS at all.
    """
    head_commit = repo.head_commit()
    assert head_commit is not None, f"{repo.name} has no commits"
    blob = repo.get_file(head_commit, file_name)
    assert isinstance(blob, str), f"{file_name} could not be read from HEAD"
    assert is_lfs_pointer(blob.encode()), (
        f"{repo.name}: {file_name} was committed as a normal blob, so this test "
        "is not exercising Git LFS"
    )


def build_lfs_origin(
    path: Path,
    other_branch: str = "other",
    payload_size: Optional[int] = None,
    extra_files: int = 0,
) -> GitRepository:
    """A standalone origin whose tracked files are stored in Git LFS.

    ``payload_size`` pads the tracked file, and ``extra_files`` adds siblings -
    both for measuring what a checkout costs.
    """

    def write(repo: GitRepository, revision: str) -> None:
        write_lfs_file(repo, revision, payload_size=payload_size)
        for index in range(extra_files):
            (repo.path / f"extra{index}.bin").write_bytes(
                get_lfs_file_content(f"{revision}-{index}")
            )

    repo = build_origin(path, write, other_branch)
    assert_committed_as_lfs_pointer(repo, LFS_FILE_NAME)
    return repo


def build_origin(
    path: Path,
    write_file: Callable[[GitRepository, str], None],
    other_branch: str = "other",
) -> GitRepository:
    """Create a standalone origin with two revisions on separate branches.

    The default branch ends at the ``v2`` payload and ``other_branch`` pins
    ``v1``, so a checkout between them has to rewrite the tracked file.
    """
    path.mkdir(parents=True, exist_ok=True)
    repo = GitRepository(path=path)
    repo.init_repo()
    write_file(repo, "v1")
    repo.commit("Add tracked file (v1)")
    repo.create_branch(other_branch)
    write_file(repo, "v2")
    repo.commit("Update tracked file (v2)")
    return repo


def enable_lfs(repo: GitRepository, lfs_url: Optional[str] = None) -> None:
    """Install the LFS filters into ``repo`` and track the LFS pattern there.

    When ``lfs_url`` is given, write a ``.lfsconfig`` pinning the LFS endpoint.
    ``.lfsconfig`` is committed, so it travels with the repository through
    clones and lets a client resolve objects from the LFS server rather than
    from whichever git remote it was cloned from.
    """
    repo._git("lfs install --local")
    repo._git("lfs track {}", LFS_TRACKED_PATTERN)
    if lfs_url is not None:
        (repo.path / ".lfsconfig").write_text(f"[lfs]\n\turl = {lfs_url}\n")


def get_lfs_file_content(revision: str) -> bytes:
    """Deterministic, recognizable payload for the LFS-tracked file.

    Padded well past a pointer file's length, and distinct per revision so a
    stale checkout is distinguishable from a missing smudge.
    """
    return f"LFS-CONTENT-{revision}-".encode() + revision.encode() * 512


def is_lfs_pointer(content: bytes) -> bool:
    """True when git-lfs itself recognizes ``content`` as a pointer file.

    Empty content is not one, and has to be rejected here: ``git lfs pointer
    --check`` exits 0 for it.
    """
    if not content:
        return False
    try:
        run("git", "lfs", "pointer", "--check", "--stdin", input=content, raw=True)
        return True
    except subprocess.CalledProcessError:
        return False


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


def write_lfs_file(
    target_repo: GitRepository,
    revision: str,
    lfs_url: Optional[str] = None,
    payload_size: Optional[int] = None,
) -> None:
    """Enable LFS in ``target_repo`` and write the tracked file for ``revision``."""
    enable_lfs(target_repo, lfs_url=lfs_url)
    content = get_lfs_file_content(revision)
    if payload_size is not None:
        content = (content * (payload_size // len(content) + 1))[:payload_size]
    (target_repo.path / LFS_FILE_NAME).write_bytes(content)
