"""What a Git LFS checkout costs, asserted rather than assumed.

Two properties this archive depends on, both of which a naive filter loses:
content is streamed rather than held in memory, so a large PDF does not size
the process; and git-lfs is spoken to over one long-running connection, so a
hundred thousand documents do not mean a hundred thousand processes.
"""

import shutil
import sys

import pytest

from taf.git import GitRepository
from taf.tests.test_updater.test_lfs.conftest import (
    LFS_FILE_NAME,
    assert_lfs_content_materialized,
    build_lfs_origin,
    checkout_in_subprocess,
    counting_git_lfs,
    lfs_file_content,
    needs_git_lfs,
    get_peak_rss_of_checkout,
)
import taf.lfs as lfs_module

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

    peak_rss_kb = get_peak_rss_of_checkout(
        checkout_in_subprocess(
            GitRepository(path=client.path), client.default_branch, LFS_FILE_NAME
        )
    )

    assert (client.path / LFS_FILE_NAME).stat().st_size == LARGE_FILE_SIZE
    assert peak_rss_kb < MEMORY_BUDGET_KB, (
        f"the checkout peaked at {peak_rss_kb / 1024:.0f} MB for a "
        f"{LARGE_FILE_SIZE / 1024 / 1024:.0f} MB file - it is being buffered "
        f"rather than streamed"
    )


@needs_git_lfs
def test_a_status_check_shares_one_git_lfs_process(tmp_path, monkeypatch):
    """A dirty-index check is a filter run too, and pays the same per-file cost.

    libgit2 runs the clean filter to decide whether a tracked file changed, and
    the updater asks this of every target repository before it checks anything
    out.
    """
    origin = build_lfs_origin(tmp_path / "origin", extra_files=MANY_FILES)
    client = GitRepository(path=tmp_path / "client")
    client.clone_from_disk(origin.path, keep_remote=True)

    tracked = sorted(client.path.glob("*.bin"))
    assert len(tracked) == MANY_FILES + 1, tracked
    for path in tracked:
        # a same-length edit, so libgit2 cannot decide by size and has to clean
        path.write_bytes(path.read_bytes().replace(b"LFS-CONTENT", b"lfs-content"))

    log = tmp_path / "spawns"
    env = counting_git_lfs(tmp_path / "shim", shutil.which("git-lfs"), log)
    for name in ("PATH", "GIT_LFS_REAL", "GIT_LFS_SPAWN_LOG"):
        monkeypatch.setenv(name, env[name])
    lfs_module.get_git_lfs_executable.cache_clear()
    try:
        assert client.something_to_commit()
    finally:
        lfs_module.get_git_lfs_executable.cache_clear()

    # one for the whole libgit2 status, one for git's own `status --porcelain`
    spawns = len(log.read_text().split())
    assert spawns == 2, (
        f"git-lfs was started {spawns} times for {len(tracked)} modified files: "
        f"more means the connection is not being reused, fewer means libgit2 "
        f"never ran the filter and this measures nothing"
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
    result = checkout_in_subprocess(
        GitRepository(path=client.path), client.default_branch, LFS_FILE_NAME, env=env
    )

    assert "RAISED:none" in result.stdout, f"the checkout failed: {result.stderr}"
    assert_lfs_content_materialized(client.path, "v2")
    for index in range(MANY_FILES):
        sibling = client.path / f"extra{index}.bin"
        assert sibling.read_bytes() == lfs_file_content(f"v2-{index}"), (
            f"{sibling.name} does not hold its content, so counting spawns says "
            f"nothing about the cost of a checkout"
        )

    spawns = len(log.read_text().split())
    assert spawns <= 2, (
        f"git-lfs was started {spawns} times for {MANY_FILES + 1} files - the "
        f"connection is not being reused"
    )
