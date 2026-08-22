"""Make libgit2 checkouts honor Git LFS, by delegating to the git-lfs binary.

Git LFS keeps a small text *pointer* in the repository and the real bytes in a
separate store, moved by the ``smudge`` and ``clean`` filters git runs on
checkout and commit. libgit2 provides a filter framework but does not execute
the external filter commands declared in git config (``filter.lfs.process`` and
friends), so files checked out through ``pygit2`` land in the working tree as
pointer text unless a filter is registered.

The filter pipes the blob through the ``git-lfs`` binary, which handles pointer
parsing, the object store, Batch API fetches and credentials.

Both directions are implemented. Without ``clean``, libgit2 compares real
working-tree bytes against a pointer blob, decides the file is modified, and
refuses to check out with "1 conflict prevents checkout".

``attributes = "filter=lfs"`` means libgit2 invokes the filter only for paths
``.gitattributes`` routes to LFS, so repositories that do not use LFS never
reach this code and do not need ``git-lfs`` installed.
"""

import shutil
import subprocess
from functools import lru_cache
from typing import List, Optional

import pygit2

from taf.exceptions import GitLFSError
from taf.log import taf_logger

FILTER_NAME = "taf-git-lfs"


class GitLFSFilter(pygit2.Filter):
    """Pipe LFS-tracked blobs through ``git-lfs smudge`` / ``git-lfs clean``."""

    attributes = "filter=lfs"

    def __init__(self):
        super().__init__()
        self._chunks: List[bytes] = []
        self._path: Optional[str] = None
        self._mode: Optional[int] = None
        self._workdir: Optional[str] = None

    def check(self, src, attr_values):
        # libgit2 reuses filter instances, so reset per stream
        self._chunks = []
        self._path = src.path
        self._mode = src.mode
        # git-lfs resolves config, the object store and the LFS endpoint
        # relative to the repository, so it has to run inside it
        repo = getattr(src, "repo", None)
        workdir = getattr(repo, "workdir", None) if repo is not None else None
        self._workdir = str(workdir) if workdir else None

    def close(self, write_next):
        payload = b"".join(self._chunks)
        if not payload:
            return
        verb = "smudge" if self._mode == pygit2.GIT_FILTER_SMUDGE else "clean"
        write_next(_run_git_lfs(verb, self._path, payload, self._workdir))

    def write(self, data, src, write_next):
        self._chunks.append(bytes(data))


def _run_git_lfs(
    verb: str, path: Optional[str], payload: bytes, workdir: Optional[str]
) -> bytes:
    """Feed ``payload`` to ``git-lfs <verb>`` and return what it produces.

    Not ``taf.utils.run``: that merges stderr into stdout, and here stdout is
    the file's content.
    """
    executable = get_git_lfs_executable()
    display_path = path or "file"
    # pygit2 discards exceptions raised inside a filter, so the reason has to be
    # logged here or it is lost
    if executable is None:
        message = (
            f"Cannot check out '{display_path}': it is stored in Git LFS, but "
            f"Git LFS is not installed. Install it from https://git-lfs.com and "
            f"try again."
        )
        taf_logger.error(message)
        raise GitLFSError(message)

    try:
        result = subprocess.run(
            [executable, verb, "--", path or ""],
            input=payload,
            capture_output=True,
            cwd=workdir,
        )
    except OSError as error:
        message = f"Could not run Git LFS for '{display_path}': {error}"
        taf_logger.error(message)
        raise GitLFSError(message) from error

    if result.returncode != 0:
        details = result.stderr.decode(errors="replace").strip()
        message = f"Git LFS could not process '{display_path}'."
        taf_logger.error("{} {}", message, details)
        raise GitLFSError(f"{message} {details}".strip())

    return result.stdout


@lru_cache(maxsize=1)
def get_git_lfs_executable() -> Optional[str]:
    """Path to the ``git-lfs`` binary, or None when it is not installed."""
    return shutil.which("git-lfs")


pygit2.filter_register(FILTER_NAME, GitLFSFilter)
