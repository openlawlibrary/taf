"""Make libgit2 checkouts honor Git LFS, by delegating to the git-lfs binary.

Git LFS keeps a small text *pointer* in the repository and the real bytes in a
separate store, moved by the ``smudge`` and ``clean`` filters git runs on
checkout and commit. libgit2 provides a filter framework but does not execute
the external filter commands declared in git config (``filter.lfs.process`` and
friends), so files checked out through ``pygit2`` land in the working tree as
pointer text unless a filter is registered.

The filter pipes the blob through the ``git-lfs`` binary, which handles pointer
parsing, the object store, Batch API fetches and credentials.

Both directions are needed: with ``clean`` missing, libgit2 compares real
working-tree bytes against a pointer blob, decides the file is modified, and
refuses to check out with "1 conflict prevents checkout".

Two conditions keep the filter out of the way: it runs only for paths
``.gitattributes`` routes to LFS (``attributes = "filter=lfs"``), and only in
repositories where git itself runs the LFS filters, so pygit2 and git agree on
what the working tree should contain.

When git-lfs cannot do its job the blob is written through unchanged. An
exception raised from a filter leaves libgit2's destination file truncated and
is then discarded, so libgit2 treats the file as filtered successfully. Passing
the bytes through instead keeps a smudge's pointer readable, and leaves a
clean's raw content different from the pointer blob, which makes libgit2 refuse
the checkout exactly as git does.
"""

import os
import shutil
import subprocess
from functools import lru_cache
from typing import Callable, List, Optional

import pygit2

from taf.exceptions import GitLFSError
from taf.log import taf_logger

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
        payload = b""
        try:
            payload = b"".join(self._chunks)
            if not payload:
                return
            verb = "smudge" if self._mode == pygit2.GIT_FILTER_SMUDGE else "clean"
            content = run_git_lfs(verb, self._path, payload, self._workdir)
        except Exception as error:
            if not payload:
                raise
            taf_logger.debug(
                "Git LFS filter passing '{}' through unfiltered: {}",
                self._path,
                error,
            )
            content = payload
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


def is_lfs_configured(workdir: str) -> bool:
    """True when git itself runs the LFS filters in ``workdir``.

    Read from ``filter.lfs.process`` on every call: a repository can route paths
    to a filter git has no definition for, and filtering where git does not
    leaves a working tree git reports as modified. The answer changes whenever
    the repository's config does, so it is not cached.

    ``git lfs install --skip-smudge`` leaves the filter configured but appends
    ``--skip``, asking for pointers rather than content.
    """
    git = shutil.which("git")
    if not workdir or git is None or get_git_lfs_executable() is None:
        return False
    try:
        result = subprocess.run(
            [git, "-C", workdir, "config", "--get", "filter.lfs.process"],
            capture_output=True,
            text=True,
            timeout=GIT_LFS_TIMEOUT,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return result.returncode == 0 and "--skip" not in result.stdout


def run_git_lfs(verb: str, path: str, payload: bytes, workdir: str) -> bytes:
    """Feed ``payload`` to ``git-lfs <verb>`` and return what it produces."""
    executable = get_git_lfs_executable()
    if executable is None:
        message = (
            f"'{path}' is stored in Git LFS, but Git LFS is not installed. "
            f"Install it from https://git-lfs.com and try again."
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
        if verb == "smudge":
            message = (
                f"Could not get the Git LFS content for '{path}'; the file is "
                f"left as a pointer. Check that the Git LFS server is reachable "
                f"and holds this object, then run 'git lfs pull'."
            )
        else:
            message = f"Git LFS could not store the content of '{path}'."
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
