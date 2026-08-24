"""What a Git LFS checkout costs, asserted rather than assumed.

Two properties this archive depends on, both of which a naive filter loses:
content is streamed rather than held in memory, so a large PDF does not size
the process; and git-lfs is spoken to over one long-running connection, so a
hundred thousand documents do not mean a hundred thousand processes.
"""

import os
import shutil
import sys

import pytest

from taf.git import GitRepository
from taf.tests.test_updater.test_lfs.conftest import (
    LFS_FILE_NAME,
    build_lfs_origin,
    get_git_lfs_version,
)
from taf.tests.test_updater.test_lfs.perf_utils import (
    counting_git_lfs,
    measure_checkout,
)

needs_git_lfs = pytest.mark.skipif(
    not get_git_lfs_version(),
    reason="git-lfs is not installed (needs the `git lfs` subcommand on PATH)",
)

#: Large enough that holding it in memory is unmistakable in the measurement.
LARGE_FILE_SIZE = 200 * 1024 * 1024

#: Headroom over the interpreter's own footprint, well under the file size.
MEMORY_BUDGET_KB = 64 * 1024

#: Enough files that per-file spawning is unambiguous.
MANY_FILES = 40


@pytest.mark.skipif(
    not sys.platform.startswith("linux"),
    reason="peak RSS is read from /proc/self/status",
)
@needs_git_lfs
def test_a_large_file_is_not_held_in_memory(tmp_path):
    """Checking out a 200 MB LFS file must not grow the process by 200 MB."""
    origin = build_lfs_origin(tmp_path / "origin", payload_size=LARGE_FILE_SIZE)
    client = GitRepository(path=tmp_path / "client")
    client.clone_from_disk(origin.path, keep_remote=True)
    client.checkout_branch("other", create=True)

    peak_rss_kb, _ = measure_checkout(
        GitRepository(path=client.path), client.default_branch, dict(os.environ)
    )

    assert (client.path / LFS_FILE_NAME).stat().st_size == LARGE_FILE_SIZE
    assert peak_rss_kb < MEMORY_BUDGET_KB, (
        f"the checkout peaked at {peak_rss_kb / 1024:.0f} MB for a "
        f"{LARGE_FILE_SIZE / 1024 / 1024:.0f} MB file; it is being buffered "
        f"rather than streamed"
    )


@needs_git_lfs
def test_many_files_share_one_git_lfs_process(tmp_path):
    """One git-lfs per repository, not one per file.

    At a hundred thousand documents the difference is the whole cost of the
    checkout: process startup dominates, and it is paid per file.
    """
    origin = build_lfs_origin(tmp_path / "origin", extra_files=MANY_FILES)
    client = GitRepository(path=tmp_path / "client")
    client.clone_from_disk(origin.path, keep_remote=True)
    client.checkout_branch("other", create=True)

    log = tmp_path / "spawns"
    env = counting_git_lfs(tmp_path / "shim", shutil.which("git-lfs"), log)
    measure_checkout(GitRepository(path=client.path), client.default_branch, env)

    spawns = len(log.read_text().split())
    assert spawns <= 2, (
        f"git-lfs was started {spawns} times for {MANY_FILES + 1} files; the "
        f"connection is not being reused"
    )
