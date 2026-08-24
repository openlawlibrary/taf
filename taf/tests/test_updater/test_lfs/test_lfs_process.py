"""The long-running git-lfs connection: its lifetime, restart and shutdown."""

import io

import pytest

from taf.git import GitRepository
from taf.lfs import record_failure, take_failures
from taf.lfs_process import (
    GitLFSProcess,
    GitLFSProcessError,
    SESSION,
    get_process_for,
    session,
)
from taf.tests.test_updater.test_lfs.conftest import (
    LFS_FILE_NAME,
    build_lfs_origin,
    get_lfs_file_content,
    needs_git_lfs,
)


@pytest.fixture
def lfs_repository(tmp_path):
    """A repository holding one LFS object, and its pointer."""
    origin = build_lfs_origin(tmp_path / "origin")
    pointer = origin.get_file(origin.head_commit(), LFS_FILE_NAME)
    return str(origin.path), pointer.encode()


@needs_git_lfs
def test_a_crashed_process_is_restarted(lfs_repository):
    """git-lfs dying must cost the file that provoked it, not the rest.

    One process serves every file of one operation, so without a restart every file
    after a crash would fail too.
    """
    workdir, pointer = lfs_repository
    process = GitLFSProcess(_git_lfs(), workdir)
    try:
        with process.filter("smudge", LFS_FILE_NAME, io.BytesIO(pointer)) as out:
            assert out.read() == get_lfs_file_content("v2")

        killed = process._process
        assert killed is not None
        killed.kill()
        killed.wait(timeout=10)

        with process.filter("smudge", LFS_FILE_NAME, io.BytesIO(pointer)) as out:
            assert out.read() == get_lfs_file_content("v2")
        assert process._process is not killed, "the dead process was reused"
    finally:
        process.close()


def test_a_failure_recorded_outside_a_session_is_not_kept(tmp_path):
    """Nothing records what nobody will collect.

    A record kept here would be raised by the next operation, against files that
    operation had materialized correctly.
    """
    workdir = str(tmp_path)
    record_failure(workdir, "file.bin")

    assert take_failures(workdir) == set()


@needs_git_lfs
def test_a_process_outside_a_session_is_not_kept(lfs_repository):
    """Nothing would close it, so it must not be pooled."""
    workdir, _ = lfs_repository
    first = get_process_for(_git_lfs(), workdir)
    second = get_process_for(_git_lfs(), workdir)
    assert first is not second
    assert not SESSION.processes


@needs_git_lfs
def test_a_session_does_not_outlive_a_config_change(lfs_repository):
    """git-lfs reads config at startup, so a process must not span operations."""
    workdir, pointer = lfs_repository
    with session():
        first = get_process_for(_git_lfs(), workdir)
        first.filter("smudge", LFS_FILE_NAME, io.BytesIO(pointer)).close()
        pid = first._process.pid if first._process else None
    with session():
        second = get_process_for(_git_lfs(), workdir)
        second.filter("smudge", LFS_FILE_NAME, io.BytesIO(pointer)).close()
        assert second._process is not None and second._process.pid != pid


@needs_git_lfs
def test_a_session_reuses_one_process_and_closes_it(lfs_repository):
    """The process lives for the operation, not for the interpreter."""
    workdir, pointer = lfs_repository
    with session():
        first = get_process_for(_git_lfs(), workdir)
        first.filter("smudge", LFS_FILE_NAME, io.BytesIO(pointer)).close()
        assert (
            get_process_for(_git_lfs(), workdir) is first
        ), "the session did not reuse it"
        started = first._process
        assert started is not None and started.poll() is None

    assert started.poll() is not None, "git-lfs outlived the operation"
    assert not SESSION.processes, "the session kept a process"


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


def test_closing_a_session_forgets_what_it_recorded(tmp_path):
    """A record lives no longer than the operation that hit it."""
    workdir = str(tmp_path)
    with session():
        record_failure(workdir, "file.bin")

    assert take_failures(workdir) == set()


@needs_git_lfs
def test_no_process_outlives_a_checkout(tmp_path):
    """Many repositories must not mean many resident git-lfs children."""
    clients = []
    for index in range(4):
        origin = build_lfs_origin(tmp_path / f"origin{index}")
        client = GitRepository(path=tmp_path / f"client{index}")
        client.clone_from_disk(origin.path, keep_remote=True)
        client.checkout_branch("other", create=True)
        clients.append(GitRepository(path=client.path))

    for client in clients:
        client.checkout_branch(client.default_branch)

    assert not SESSION.processes, (
        f"{len(SESSION.processes)} git-lfs processes are still held after "
        f"{len(clients)} checkouts"
    )


@needs_git_lfs
def test_one_process_serves_many_files(lfs_repository):
    """The connection is reused rather than reopened per file."""
    workdir, pointer = lfs_repository
    process = GitLFSProcess(_git_lfs(), workdir)
    try:
        for _ in range(5):
            with process.filter("smudge", LFS_FILE_NAME, io.BytesIO(pointer)) as out:
                assert out.read() == get_lfs_file_content("v2")
        assert process._process is not None and process._process.poll() is None
    finally:
        process.close()


def _git_lfs() -> str:
    from taf.lfs import get_git_lfs_executable

    executable = get_git_lfs_executable()
    assert executable is not None
    return executable
