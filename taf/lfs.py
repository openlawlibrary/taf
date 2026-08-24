"""Make libgit2 checkouts honor Git LFS, by delegating to the git-lfs binary.

Git LFS keeps a small text *pointer* in the repository and the real bytes in a
separate store, moved by the ``smudge`` and ``clean`` filters git runs on
checkout and commit. libgit2 provides a filter framework but does not execute
the external filter commands declared in git config (``filter.lfs.process`` and
friends), so files checked out through ``pygit2`` land in the working tree as
pointer text unless a filter is registered.

The filter pipes the blob through the ``git-lfs`` binary, which handles pointer
parsing, the object store, Batch API fetches and credentials. One long-running
``git-lfs filter-process`` serves a whole repository, as git's own does, and
content is staged - in memory up to a few megabytes, on disk beyond - so
neither a hundred thousand small files nor a single large one sizes the process.

Both directions are needed: ``clean`` is what makes libgit2 see an LFS file in
the working tree as unmodified.

When git-lfs cannot do its job the blob is written through unchanged. An
exception raised from a filter leaves libgit2's destination file truncated, and
so does forwarding part of a result before the rest fails, so nothing is
forwarded until the whole result is in hand. A smudge then keeps a readable
pointer, and a clean yields bytes that differ from the pointer blob, so libgit2
refuses the checkout as git does.

Two conditions keep the filter out of the way: it runs only for paths
``.gitattributes`` routes to LFS (``attributes = "filter=lfs"``), and only in a
direction where git is configured to run git-lfs itself. ``git lfs install
--skip-smudge`` disables one direction and not the other, and a repository may
define ``filter.lfs.smudge``/``clean`` without ``filter.lfs.process``.
"""

import os
import shlex
import shutil
import subprocess
from functools import lru_cache
from pathlib import Path
from tempfile import SpooledTemporaryFile
from typing import IO, Callable, List, Optional, Set, Tuple

import pygit2

from taf.exceptions import GitLFSError
from taf.lfs_process import CHUNK, POOL, SPOOL_LIMIT, GitLFSProcessError
from taf.log import taf_logger

FILTER_NAME = "taf-git-lfs"

#: Seconds a `git config` read may take. Short: it is local and runs per stream.
GIT_CONFIG_TIMEOUT = 30

#: Repositories already reported as needing git-lfs, so the warning is not
#: repeated for every file.
_reported_missing_binary: Set[str] = set()


class GitLFSFilter(pygit2.Filter):
    """Pipe LFS-tracked blobs through ``git-lfs smudge`` / ``git-lfs clean``."""

    attributes = "filter=lfs"

    def __init__(self) -> None:
        super().__init__()
        self._staged: IO[bytes] = SpooledTemporaryFile(  # type: ignore[assignment]
            max_size=SPOOL_LIMIT
        )
        self._path: str = ""
        self._mode: int = pygit2.GIT_FILTER_SMUDGE
        self._workdir: str = ""

    def check(self, src: "pygit2.FilterSource", attr_values: List[str]) -> None:
        workdir = str(src.repo.workdir) if src.repo.workdir else ""
        smudge_command, clean_command = get_lfs_filter_commands(workdir)
        wanted = (
            smudge_command if src.mode == pygit2.GIT_FILTER_SMUDGE else clean_command
        )
        if not wanted:
            warn_once_if_git_lfs_is_missing(workdir)
            raise pygit2.Passthrough
        self._staged = SpooledTemporaryFile(  # type: ignore[assignment]
            max_size=SPOOL_LIMIT
        )
        self._path = src.path
        self._mode = src.mode
        self._workdir = workdir

    def close(self, write_next: Callable[[bytes], None]) -> None:
        if self._staged.tell() == 0:
            self._staged.close()
            return
        verb = "smudge" if self._mode == pygit2.GIT_FILTER_SMUDGE else "clean"
        self._staged.seek(0)
        try:
            filtered = filter_through_git_lfs(
                verb, self._path, self._staged, self._workdir
            )
        except GitLFSError:
            # nothing has been forwarded yet, so the unfiltered blob is still a
            # safe answer: for a smudge that is the pointer, and for a clean it
            # is content libgit2 will not mistake for the pointer blob
            self._staged.seek(0)
            filtered = self._staged
        try:
            for chunk in iter(lambda: filtered.read(CHUNK), b""):
                write_next(chunk)
        finally:
            filtered.close()
            self._staged.close()

    def write(
        self,
        data: bytes,
        src: "pygit2.FilterSource",
        write_next: Callable[[bytes], None],
    ) -> None:
        self._staged.write(data)


def _git_lfs_only(command: str) -> str:
    """``command`` when it invokes this process's git-lfs, "" otherwise.

    A repository can point ``filter.lfs.*`` at any program, including a wrapper
    whose name merely contains "git-lfs"; running git-lfs for one of those would
    put bytes in the working tree that git never wrote. The program is resolved
    and compared, rather than matched as text.
    """
    executable = get_git_lfs_executable()
    if not command or executable is None:
        return ""
    try:
        argv = shlex.split(command, posix=os.name != "nt")
    except ValueError:
        return ""
    if not argv:
        return ""
    resolved = shutil.which(argv[0])
    if resolved and os.path.realpath(resolved) == os.path.realpath(executable):
        return command
    # the `git lfs <verb>` spelling reaches the same binary through git itself
    if len(argv) > 1 and argv[1] == "lfs":
        git = shutil.which(argv[0])
        if git and Path(git).stem == "git":
            return command
    return ""


@lru_cache(maxsize=1)
def get_git_lfs_executable() -> Optional[str]:
    """Path to the ``git-lfs`` binary, or None when it is not installed."""
    return shutil.which("git-lfs")


def get_lfs_filter_commands(workdir: str) -> Tuple[str, str]:
    """The git-lfs smudge and clean commands git runs in ``workdir``, else "".

    ``filter.lfs.process`` drives both directions; ``filter.lfs.smudge`` and
    ``filter.lfs.clean`` are the older per-direction form. A ``--skip`` in the
    smudge command is ``git lfs install --skip-smudge``, which asks for pointers
    in the working tree while still writing pointers into the object database.
    """
    git = shutil.which("git")
    if not workdir or git is None or get_git_lfs_executable() is None:
        return "", ""

    process = read_git_config(git, workdir, "filter.lfs.process")
    smudge = _git_lfs_only(
        process or read_git_config(git, workdir, "filter.lfs.smudge")
    )
    clean = _git_lfs_only(process or read_git_config(git, workdir, "filter.lfs.clean"))
    if "--skip" in smudge:
        smudge = ""
    return smudge, clean


def filter_through_git_lfs(
    verb: str, path: str, source: IO[bytes], workdir: str
) -> IO[bytes]:
    """Run ``git-lfs <verb>`` over ``source`` and return a rewound result stream."""
    executable = get_git_lfs_executable()
    if executable is None:
        message = (
            f"'{path}' is stored in Git LFS, but Git LFS is not installed. "
            f"Install it from https://git-lfs.com and try again."
        )
        taf_logger.error(message)
        raise GitLFSError(message)

    process = POOL.acquire(executable, workdir)
    try:
        return process.filter(verb, path, source)
    except GitLFSProcessError as error:
        if verb == "smudge":
            message = (
                f"Could not get the Git LFS content for '{path}'; the file is "
                f"left as a pointer. Check that the Git LFS server is reachable "
                f"and holds this object, then run 'git lfs pull'."
            )
        else:
            message = (
                f"Git LFS could not store the content of '{path}'; the file is "
                f"left as it is. Check that '.git/lfs' is writable."
            )
        taf_logger.error(message)
        taf_logger.debug("git-lfs {} failed: {}", verb, error)
        raise GitLFSError(message) from error
    finally:
        POOL.release(process)


def read_git_config(git: str, workdir: str, key: str) -> str:
    """Value git resolves for ``key`` in ``workdir``, "" when unset or unreadable.

    Not ``taf.utils.run``: it applies ``str.format`` to every argument, which
    raises on a path containing a brace, and an exception here reaches libgit2
    as a truncated file.
    """
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


def warn_once_if_git_lfs_is_missing(workdir: str) -> None:
    """Say so when a repository wants Git LFS and the binary is not installed.

    Once per repository: the alternative is a line per file, and an archive can
    hold a hundred thousand of them.
    """
    git = shutil.which("git")
    if not workdir or git is None or get_git_lfs_executable() is not None:
        return
    if workdir in _reported_missing_binary:
        return
    configured = read_git_config(git, workdir, "filter.lfs.process") or read_git_config(
        git, workdir, "filter.lfs.smudge"
    )
    if not configured:
        return
    _reported_missing_binary.add(workdir)
    taf_logger.warning(
        "{} stores files in Git LFS, but Git LFS is not installed, so they will "
        "be checked out as pointer files. Install it from https://git-lfs.com "
        "and run 'git lfs pull'.",
        workdir,
    )


pygit2.filter_register(FILTER_NAME, GitLFSFilter)
