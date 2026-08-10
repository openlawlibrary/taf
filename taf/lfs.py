"""Make libgit2 checkouts honor Git LFS, by delegating to the git-lfs binary.

Git LFS keeps a small text *pointer* in the repository and the real bytes in a
separate store, moved by the ``smudge``/``clean`` filters git runs on
checkout/commit. libgit2 provides a filter framework but deliberately does not
execute the external filter commands declared in git config
(``filter.lfs.process`` and friends), so anything TAF checks out through
``pygit2`` would land in the working tree as pointer text.

Rather than reimplement Git LFS - pointer parsing, the object store, the Batch
API, credential handling - this registers a filter that pipes the blob through
the real ``git-lfs`` binary, which already does all of that, including fetching
from the LFS server when an object is not cached locally.

Both directions must be implemented, not just ``smudge``. If ``clean`` is left
out, libgit2 compares real working-tree bytes against a pointer blob, concludes
the file is modified, and refuses to check out with "1 conflict prevents
checkout".

The filter declares ``attributes = "filter=lfs"``, so libgit2 invokes it only
for paths ``.gitattributes`` routes to LFS. Repositories that do not use LFS
never reach this code, which is what keeps ``git-lfs`` an optional dependency.
"""

import shutil
import subprocess
from functools import lru_cache
from typing import Optional

from taf.exceptions import GitLFSError
from taf.log import taf_logger

try:
    import pygit2

    #: The filter API landed in pygit2 1.13.3.
    FILTER_API_AVAILABLE = hasattr(pygit2, "filter_register")
except ImportError:  # pragma: no cover - pygit2 is a hard dependency
    pygit2 = None  # type: ignore[assignment]
    FILTER_API_AVAILABLE = False

FILTER_NAME = "taf-git-lfs"

#: git-lfs pointer files start with this; used to sanity-check smudge input.
POINTER_PREFIX = b"version https://git-lfs"

_registered = False


@lru_cache(maxsize=1)
def git_lfs_executable() -> Optional[str]:
    """Path to the ``git-lfs`` binary, or None when it is not installed.

    Cached because it is consulted once per filtered file. Tests replace this
    function to simulate a machine without git-lfs.
    """
    return shutil.which("git-lfs")


if FILTER_API_AVAILABLE:

    class GitLFSFilter(pygit2.Filter):  # type: ignore[name-defined,misc]
        """Pipe LFS-tracked blobs through ``git-lfs smudge`` / ``git-lfs clean``."""

        attributes = "filter=lfs"

        def __init__(self):
            super().__init__()
            self._chunks: list = []
            self._path: Optional[str] = None
            self._mode: Optional[int] = None
            self._workdir: Optional[str] = None

        def check(self, src, attr_values):
            # Reset per stream: libgit2 reuses filter instances.
            self._chunks = []
            self._path = src.path
            self._mode = src.mode
            # git-lfs resolves config, the object store and the LFS endpoint
            # relative to the repository, so it has to run inside it.
            repo = getattr(src, "repo", None)
            workdir = getattr(repo, "workdir", None) if repo is not None else None
            self._workdir = str(workdir) if workdir else None

        def write(self, data, src, write_next):
            self._chunks.append(bytes(data))

        def close(self, write_next):
            payload = b"".join(self._chunks)
            if not payload:
                return

            verb = "smudge" if self._mode == pygit2.GIT_FILTER_SMUDGE else "clean"
            executable = git_lfs_executable()
            if executable is None:
                # pygit2 discards this exception (the caller sees "failed to
                # close filter stream"), so state the real reason in the log or
                # it is lost. Failing is deliberate: silently writing pointer
                # text produces a working tree that looks fine and is not.
                taf_logger.error(
                    "Cannot check out {}: it is tracked by Git LFS but the "
                    "git-lfs binary was not found on PATH. Install Git LFS "
                    "(https://git-lfs.com) and retry.",
                    self._path,
                )
                raise GitLFSError(
                    f"git-lfs is required to check out {self._path} but is not installed"
                )

            try:
                result = subprocess.run(
                    [executable, verb, "--", self._path or ""],
                    input=payload,
                    capture_output=True,
                    cwd=self._workdir,
                )
            except OSError as error:
                taf_logger.error(
                    "Could not run git-lfs {} for {}: {}", verb, self._path, error
                )
                raise GitLFSError(f"could not run git-lfs {verb}: {error}") from error

            if result.returncode != 0:
                stderr = result.stderr.decode(errors="replace").strip()
                taf_logger.error(
                    "git-lfs {} failed for {}: {}", verb, self._path, stderr
                )
                raise GitLFSError(f"git-lfs {verb} failed for {self._path}: {stderr}")

            if verb == "smudge" and result.stdout.startswith(POINTER_PREFIX):
                # git-lfs exits 0 and echoes the pointer back when it cannot
                # obtain the object. Refuse it rather than write it to disk.
                taf_logger.error(
                    "git-lfs could not resolve the LFS object for {}; the "
                    "working tree would be left holding a pointer file. Check "
                    "that the LFS server is reachable and holds the object.",
                    self._path,
                )
                raise GitLFSError(
                    f"git-lfs could not resolve LFS object for {self._path}"
                )

            write_next(result.stdout)


def register_lfs_filter() -> bool:
    """Register the LFS filter with libgit2, once per process.

    Returns True when the filter is registered and False when this pygit2 is too
    old to support filters (in which case pygit2 checkouts of LFS-tracked files
    keep their old behavior of writing pointer text).

    Deliberately does *not* depend on git-lfs being installed: the filter only
    runs for LFS-tracked paths, so registering unconditionally is what lets a
    repository that uses LFS report a clear error, while repositories that do
    not are unaffected. pygit2 documents the filter registry as not
    thread-safe, so this is called at import time, before any repository object
    or worker thread exists.
    """
    global _registered
    if _registered:
        return True
    if not FILTER_API_AVAILABLE:
        taf_logger.debug(
            "pygit2 {} has no filter API; Git LFS content will not be "
            "materialized by pygit2 checkouts",
            getattr(pygit2, "__version__", "unknown"),
        )
        return False
    try:
        pygit2.filter_register(FILTER_NAME, GitLFSFilter)
    except (ValueError, KeyError) as error:
        # already registered (e.g. module reloaded) - harmless
        taf_logger.debug("Git LFS filter already registered: {}", error)
    _registered = True
    return True
