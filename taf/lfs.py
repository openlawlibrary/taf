"""Make libgit2 checkouts honor Git LFS, by delegating to the git-lfs binary.

Git LFS keeps a small text *pointer* in the repository and the real bytes in a
separate store, moved by the ``smudge`` and ``clean`` filters git runs on
checkout and commit. libgit2 provides a filter framework but does not execute
the external filter commands declared in git config (``filter.lfs.process`` and
friends), so files checked out through ``pygit2`` land in the working tree as
pointer text unless a filter is registered.

The filter pipes the blob through the ``git-lfs`` binary, which handles pointer
parsing, the object store, Batch API fetches and credentials.

Both directions are needed: ``clean`` is what makes libgit2 see an LFS file in
the working tree as unmodified.

Two conditions keep the filter out of the way: it runs only for paths
``.gitattributes`` routes to LFS (``attributes = "filter=lfs"``), and only in a
direction where git is configured to run git-lfs itself, so pygit2 and git agree on
what the working tree and the object database should contain. ``git lfs install
--skip-smudge`` disables one direction and not the other, and a repository may
define ``filter.lfs.smudge``/``clean`` without ``filter.lfs.process``.

When git-lfs cannot do its job the blob is written through unchanged: an
exception raised from a filter leaves libgit2's destination file truncated. A
smudge then keeps a readable pointer, and a clean yields bytes that differ from
the pointer blob, so libgit2 refuses the checkout as git does.
"""

import os
import shlex
import shutil
import subprocess
from functools import lru_cache
from pathlib import Path
from typing import Callable, List, Optional, Set, Tuple

import pygit2

from taf.exceptions import GitLFSError
from taf.log import taf_logger

FILTER_NAME = "taf-git-lfs"

#: Seconds a single git-lfs invocation may take before it is abandoned.
GIT_LFS_TIMEOUT = 300

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
        self._chunks: List[bytes] = []
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
                f"Git LFS could not store the content of '{path}'; the file "
                f"is left as it is. Check that '.git/lfs' is writable."
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
