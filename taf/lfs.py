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
the direction git itself filters in that repository, so pygit2 and git agree on
what the working tree and the object database should contain. ``git lfs install
--skip-smudge`` disables one direction and not the other, and a repository may
define ``filter.lfs.smudge``/``clean`` without ``filter.lfs.process``.

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
from typing import Callable, List, Optional, Tuple

import pygit2

from taf.exceptions import GitLFSError
from taf.log import taf_logger

FILTER_NAME = "taf-git-lfs"

#: Seconds a single git-lfs invocation may take before it is abandoned.
GIT_LFS_TIMEOUT = 300

#: Seconds a `git config` read may take. Short: it is local and runs per stream.
GIT_CONFIG_TIMEOUT = 30


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
        smudge_command, clean_command = lfs_filter_commands(workdir)
        wanted = (
            smudge_command if src.mode == pygit2.GIT_FILTER_SMUDGE else clean_command
        )
        if not wanted:
            raise pygit2.Passthrough
        self._chunks = []
        self._path = src.path
        self._mode = src.mode
        self._workdir = workdir

    def close(self, write_next: Callable[[bytes], None]) -> None:
        payload = b"".join(self._chunks)
        if not payload:
            return
        try:
            verb = "smudge" if self._mode == pygit2.GIT_FILTER_SMUDGE else "clean"
            content = run_git_lfs(verb, self._path, payload, self._workdir)
        except Exception as error:
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
    """True when git runs a Git LFS filter in ``workdir``, in either direction."""
    return any(lfs_filter_commands(workdir))


def lfs_filter_commands(workdir: str) -> Tuple[str, str]:
    """The smudge and clean commands git runs in ``workdir``, "" where it runs none.

    Read on every call: a repository can route paths to a filter git has no
    definition for, and filtering where git does not leaves a working tree git
    reports as modified, or writes raw content where a pointer belongs.

    ``filter.lfs.process`` drives both directions; ``filter.lfs.smudge`` and
    ``filter.lfs.clean`` are the older per-direction form. A ``--skip`` in the
    smudge command is ``git lfs install --skip-smudge`` asking for pointers.
    """
    git = shutil.which("git")
    if not workdir or git is None or get_git_lfs_executable() is None:
        return "", ""

    def configured(key: str) -> str:
        try:
            result = subprocess.run(
                [git, "-C", workdir, "config", "--get", key],
                capture_output=True,
                text=True,
                timeout=GIT_CONFIG_TIMEOUT,
            )
        except (OSError, subprocess.SubprocessError) as error:
            taf_logger.debug("Could not read {} in {}: {}", key, workdir, error)
            return ""
        return result.stdout.strip() if result.returncode == 0 else ""

    process = configured("filter.lfs.process")
    smudge = process or configured("filter.lfs.smudge")
    clean = process or configured("filter.lfs.clean")
    if "--skip" in smudge:
        smudge = ""
    return smudge, clean


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
            message = (
                f"Git LFS could not store the content of '{path}'; the file is "
                f"left as it is and the operation is refused. Check that "
                f"'.git/lfs' is writable."
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
