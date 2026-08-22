"""Make libgit2 checkouts honor Git LFS, by delegating to the git-lfs binary.

Git LFS keeps a small text *pointer* in the repository and the real bytes in a
separate store, moved by the ``smudge`` and ``clean`` filters git runs on
checkout and commit. libgit2 provides a filter framework but does not execute
the external filter commands declared in git config (``filter.lfs.process`` and
friends), so files checked out through ``pygit2`` land in the working tree as
pointer text unless a filter is registered.

The filter pipes the blob through the ``git-lfs`` binary, which handles pointer
parsing, the object store, Batch API fetches and credentials.

The ``clean`` direction matters as much as ``smudge``: without it libgit2
compares real working-tree bytes against a pointer blob, decides the file is
modified, and refuses to check out with "1 conflict prevents checkout".

Two conditions keep the filter out of the way. It runs only for paths
``.gitattributes`` routes to LFS (``attributes = "filter=lfs"``), and only in
repositories where git itself would run the LFS filters, so pygit2 and git agree
on what the working tree should contain. A smudge that cannot produce content
passes the pointer through rather than raising, because an exception leaves
libgit2's destination file truncated.
"""

import os
import shutil
import subprocess
from functools import lru_cache
from typing import Callable, List, Optional

import pygit2

from taf.exceptions import GitLFSError
from taf.log import taf_logger
from taf.utils import run

FILTER_NAME = "taf-git-lfs"

#: Seconds a single git-lfs invocation may take before it is abandoned.
GIT_LFS_TIMEOUT = 300


class GitLFSFilter(pygit2.Filter):
    """Pipe LFS-tracked blobs through ``git-lfs smudge`` / ``git-lfs clean``."""

    attributes = "filter=lfs"

    def __init__(self) -> None:
        super().__init__()
        self._chunks: List[bytes] = []
        self._path: str = ""
        self._mode: int = pygit2.GIT_FILTER_SMUDGE
        self._workdir: str = ""

    def check(self, src: "pygit2.FilterSource", attr_values: List[str]) -> None:
        workdir = str(src.repo.workdir) if src.repo.workdir else ""
        if not is_lfs_configured(workdir):
            raise pygit2.Passthrough
        self._chunks = []
        self._path = src.path
        self._mode = src.mode
        self._workdir = workdir

    def close(self, write_next: Callable[[bytes], None]) -> None:
        payload = b"".join(self._chunks)
        if not payload:
            return
        smudge = self._mode == pygit2.GIT_FILTER_SMUDGE
        try:
            content = run_git_lfs(
                "smudge" if smudge else "clean", self._path, payload, self._workdir
            )
        except GitLFSError:
            if not smudge:
                raise
            # Raising leaves libgit2's destination file truncated. Writing the
            # pointer through keeps the file readable, and `git lfs pull` fills
            # it in once the object is reachable.
            write_next(payload)
            return
        write_next(content)

    def write(
        self,
        data: bytes,
        src: "pygit2.FilterSource",
        write_next: Callable[[bytes], None],
    ) -> None:
        self._chunks.append(bytes(data))


@lru_cache(maxsize=1)
def get_git_lfs_executable() -> Optional[str]:
    """Path to the ``git-lfs`` binary, or None when it is not installed."""
    return shutil.which("git-lfs")


@lru_cache(maxsize=None)
def is_lfs_configured(workdir: str) -> bool:
    """True when git itself would run the LFS filters in ``workdir``.

    Keyed on ``filter.lfs.process`` rather than on the ``.gitattributes``
    attribute alone: a repository can route paths to a filter that git has no
    definition for, and smudging where git would not leaves a working tree git
    reports as modified.
    """
    if not workdir or get_git_lfs_executable() is None:
        return False
    try:
        run("git", "-C", workdir, "config", "--get", "filter.lfs.process")
    except subprocess.CalledProcessError:
        return False
    return True


def run_git_lfs(verb: str, path: str, payload: bytes, workdir: str) -> bytes:
    """Feed ``payload`` to ``git-lfs <verb>`` and return what it produces."""
    executable = get_git_lfs_executable()
    if executable is None:
        message = (
            f"Cannot check out '{path}': it is stored in Git LFS, but Git LFS "
            f"is not installed. Install it from https://git-lfs.com and try "
            f"again."
        )
        taf_logger.error(message)
        raise GitLFSError(message)

    try:
        result = subprocess.run(
            [executable, verb, "--", path],
            input=payload,
            capture_output=True,
            cwd=workdir,
            timeout=GIT_LFS_TIMEOUT,
            # a credential prompt would block a checkout indefinitely
            env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        message = f"Could not run Git LFS for '{path}'."
        taf_logger.error(message)
        taf_logger.debug("git-lfs {} failed to run: {}", verb, error)
        raise GitLFSError(message) from error

    if result.returncode != 0:
        message = (
            f"Could not get the Git LFS content for '{path}'. Check that the "
            f"Git LFS server is reachable and holds this object."
        )
        taf_logger.error(message)
        taf_logger.debug(
            "git-lfs {} exited {}: {}",
            verb,
            result.returncode,
            result.stderr.decode(errors="replace").strip(),
        )
        raise GitLFSError(message)

    return result.stdout


pygit2.filter_register(FILTER_NAME, GitLFSFilter)
