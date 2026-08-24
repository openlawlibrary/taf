"""The long-running git-lfs connection: restart, retry and shutdown."""

import io
import subprocess
import sys

import pytest

from taf.lfs_process import POOL, GitLFSProcess, GitLFSProcessError
from taf.tests.test_updater.test_lfs.conftest import (
    LFS_FILE_NAME,
    build_lfs_origin,
    get_git_lfs_version,
    lfs_file_content,
)

needs_git_lfs = pytest.mark.skipif(
    not get_git_lfs_version(),
    reason="git-lfs is not installed (needs the `git lfs` subcommand on PATH)",
)


@pytest.fixture
def lfs_repository(tmp_path):
    """A repository holding one LFS object, and its pointer."""
    origin = build_lfs_origin(tmp_path / "origin")
    pointer = origin.get_file(origin.head_commit(), LFS_FILE_NAME)
    return str(origin.path), pointer.encode()


@needs_git_lfs
def test_one_process_serves_many_files(lfs_repository):
    """The connection is reused rather than reopened per file."""
    workdir, pointer = lfs_repository
    process = GitLFSProcess(_git_lfs(), workdir)
    try:
        for _ in range(5):
            with process.filter("smudge", LFS_FILE_NAME, io.BytesIO(pointer)) as out:
                assert out.read() == lfs_file_content("v2")
        assert process._process is not None and process._process.poll() is None
    finally:
        process.close()


@needs_git_lfs
def test_a_crashed_process_is_restarted(lfs_repository):
    """git-lfs dying must cost the file that provoked it, not the rest.

    One process serves a whole repository, so without a restart every file
    after a crash would fail too.
    """
    workdir, pointer = lfs_repository
    process = GitLFSProcess(_git_lfs(), workdir)
    try:
        with process.filter("smudge", LFS_FILE_NAME, io.BytesIO(pointer)) as out:
            assert out.read() == lfs_file_content("v2")

        killed = process._process
        assert killed is not None
        killed.kill()
        killed.wait(timeout=10)

        with process.filter("smudge", LFS_FILE_NAME, io.BytesIO(pointer)) as out:
            assert out.read() == lfs_file_content("v2")
        assert process._process is not killed, "the dead process was reused"
    finally:
        process.close()


@needs_git_lfs
def test_an_unusable_executable_is_reported(tmp_path, lfs_repository):
    """Something that is not git-lfs must fail cleanly, not hang."""
    workdir, pointer = lfs_repository
    not_git_lfs = tmp_path / "not-git-lfs"
    not_git_lfs.write_text("#!/bin/sh\nexit 9\n")
    not_git_lfs.chmod(0o755)

    process = GitLFSProcess(str(not_git_lfs), workdir)
    try:
        with pytest.raises(GitLFSProcessError):
            process.filter("smudge", LFS_FILE_NAME, io.BytesIO(pointer))
    finally:
        process.close()


@needs_git_lfs
def test_the_pool_hands_out_one_process_at_a_time(lfs_repository):
    """Two callers must not share a connection: it carries one exchange."""
    workdir, _ = lfs_repository
    first = POOL.acquire(_git_lfs(), workdir)
    second = POOL.acquire(_git_lfs(), workdir)
    assert first is not second

    POOL.release(first)
    assert (
        POOL.acquire(_git_lfs(), workdir) is first
    ), "a released process was not reused"
    POOL.close_all()


@needs_git_lfs
def test_close_all_terminates_pooled_processes(lfs_repository):
    """Nothing is left running once the pool is closed."""
    workdir, pointer = lfs_repository
    process = POOL.acquire(_git_lfs(), workdir)
    process.filter("smudge", LFS_FILE_NAME, io.BytesIO(pointer)).close()
    started = process._process
    assert started is not None and started.poll() is None
    POOL.release(process)

    POOL.close_all()

    assert started.poll() is not None, "git-lfs is still running after close_all()"


@needs_git_lfs
def test_the_interpreter_exits_cleanly_with_a_live_connection(tmp_path, lfs_repository):
    """A pooled process must not keep the interpreter from exiting.

    The pool outlives the operation that filled it, so it is closed by an
    atexit hook; without one this either leaks or hangs on shutdown.
    """
    workdir, _ = lfs_repository
    script = (
        "from taf.lfs_process import POOL\n"
        f"process = POOL.acquire({_git_lfs()!r}, {workdir!r})\n"
        "process._ensure_started()\n"
        "POOL.release(process)\n"
        "print('acquired')\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", script], capture_output=True, text=True, timeout=60
    )

    assert result.returncode == 0, result.stderr
    assert "acquired" in result.stdout


def _git_lfs() -> str:
    from taf.lfs import get_git_lfs_executable

    executable = get_git_lfs_executable()
    assert executable is not None
    return executable
