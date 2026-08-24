"""A ``git-lfs filter-process`` scoped to one libgit2 operation.

A process belongs to a *session*: opened by the code that starts a libgit2
operation, used for every file of it, and closed when it ends - the lifetime
git itself gives a filter process. A shorter one costs a process launch per
file, and an archive holds a hundred thousand of them; a longer one holds a
child open per repository and pins the configuration git-lfs read at startup,
including the repository's committed ``.lfsconfig``, which moves with a
checkout.

Sessions are thread-local, because a pkt-line connection carries one exchange at
a time and the updater materializes repositories concurrently.

Content is streamed both ways and staged before it is handed on, so nothing is
held whole in memory and nothing partial is emitted.
"""

import subprocess
import threading
from contextlib import contextmanager
from tempfile import SpooledTemporaryFile
from typing import IO, Dict, Iterator, List, Optional, Set

from taf.lfs_protocol import (
    FLUSH,
    encode_stream,
    encode_text,
    read_packet,
    read_text_section,
)
from taf.log import taf_logger

#: Bytes of a filtered file kept in memory before spilling to disk. Small files
#: never touch the disk; a large one costs this much resident, not its size.
SPOOL_LIMIT = 5 * 1024 * 1024

#: Read size when moving staged content on.
CHUNK = 1024 * 1024

#: Seconds to wait for a filter process to exit before killing it.
SHUTDOWN_TIMEOUT = 10


class GitLFSProcessError(Exception):
    """The filter process could not be started, or stopped responding."""


class _ConnectionLost(Exception):
    """The exchange broke, as opposed to git-lfs answering with an error."""


class GitLFSProcess:
    """One ``git-lfs filter-process``, driven over pkt-line."""

    def __init__(self, executable: str, workdir: str):
        self.executable = executable
        self.workdir = workdir
        self._process: Optional[subprocess.Popen] = None

    def close(self) -> None:
        process, self._process = self._process, None
        if process is None:
            return
        try:
            if process.stdin:
                process.stdin.close()
            process.wait(timeout=SHUTDOWN_TIMEOUT)
        except (OSError, subprocess.SubprocessError):
            process.kill()
            try:
                # without this the child stays a zombie for the process's life
                process.wait(timeout=SHUTDOWN_TIMEOUT)
            except subprocess.SubprocessError:
                taf_logger.debug("git-lfs did not exit after being killed")

    def filter(self, verb: str, path: str, source: IO[bytes]) -> IO[bytes]:
        """Run ``verb`` over ``source``; return a rewound stream of the result.

        A connection that was already open and then broke is retried once on a
        fresh process: one process serves many files, so a crash would otherwise
        fail every file after it. A process that breaks on its first exchange is
        not retried - git-lfs exits rather than reporting a per-file error, so
        retrying would repeat the work, and the network attempts, for a file it
        has already refused.
        """
        reused = self._process is not None and self._process.poll() is None
        try:
            return self._exchange(verb, path, source)
        except _ConnectionLost as error:
            self.close()
            if not reused:
                raise GitLFSProcessError(
                    f"git-lfs {verb} of '{path}' failed: {error}"
                ) from error
            taf_logger.debug("git-lfs connection lost, retrying once: {}", error)
        source.seek(0)
        try:
            return self._exchange(verb, path, source)
        except _ConnectionLost as error:
            self.close()
            raise GitLFSProcessError(
                f"git-lfs {verb} of '{path}' failed: {error}"
            ) from error

    def _exchange(self, verb: str, path: str, source: IO[bytes]) -> IO[bytes]:
        try:
            process = self._ensure_started()
        except GitLFSProcessError as error:
            raise _ConnectionLost(str(error)) from error
        if process.stdin is None or process.stdout is None:
            raise _ConnectionLost("git-lfs was started without pipes")
        stdin, stdout = process.stdin, process.stdout
        try:
            stdin.write(encode_text(f"command={verb}"))
            stdin.write(encode_text(f"pathname={path}"))
            stdin.write(FLUSH)
            for chunk in iter(lambda: source.read(CHUNK), b""):
                for packet in encode_stream(chunk):
                    stdin.write(packet)
            stdin.write(FLUSH)
            stdin.flush()

            self._expect_success(read_text_section(stdout), verb, path)
            staged: IO[bytes] = SpooledTemporaryFile(  # type: ignore[assignment]
                max_size=SPOOL_LIMIT
            )
            # packet by packet, so the file is never held whole in memory
            for packet in iter(lambda: read_packet(stdout), None):
                staged.write(packet)
            self._expect_success(read_text_section(stdout), verb, path)
        except (EOFError, OSError, ValueError) as error:
            raise _ConnectionLost(str(error)) from error
        staged.seek(0)
        return staged

    def _ensure_started(self) -> subprocess.Popen:
        if self._process is not None and self._process.poll() is None:
            return self._process
        self._process = None
        try:
            process = subprocess.Popen(
                [self.executable, "filter-process"],
                cwd=self.workdir,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
            )
        except OSError as error:
            raise GitLFSProcessError(f"could not start git-lfs: {error}") from error
        try:
            self._handshake(process)
        except (EOFError, OSError) as error:
            process.kill()
            process.wait(timeout=SHUTDOWN_TIMEOUT)
            raise GitLFSProcessError(f"git-lfs did not start: {error}") from error
        self._process = process
        return process

    @staticmethod
    def _expect_success(status: List[str], verb: str, path: str) -> None:
        if "status=success" not in status:
            raise _ConnectionLost(
                f"git-lfs {verb} of '{path}' reported {status or ['no status']}"
            )

    @staticmethod
    def _handshake(process: subprocess.Popen) -> None:
        if process.stdin is None or process.stdout is None:
            raise EOFError("git-lfs was started without pipes")
        process.stdin.write(encode_text("git-filter-client"))
        process.stdin.write(encode_text("version=2"))
        process.stdin.write(FLUSH)
        process.stdin.flush()
        hello = read_text_section(process.stdout)
        if "git-filter-server" not in hello or "version=2" not in hello:
            raise EOFError(f"unexpected greeting: {hello}")
        process.stdin.write(encode_text("capability=clean"))
        process.stdin.write(encode_text("capability=smudge"))
        process.stdin.write(FLUSH)
        process.stdin.flush()
        read_text_section(process.stdout)


class _Session(threading.local):
    """Per-thread state for the libgit2 operation currently running."""

    def __init__(self) -> None:
        self.depth = 0
        self.processes: Dict[str, GitLFSProcess] = {}
        self.commands: Dict[str, object] = {}
        self.failures: Dict[str, Set[str]] = {}


SESSION = _Session()


@contextmanager
def session() -> Iterator[None]:
    """Scope the filter processes and lookups of one libgit2 operation.

    Re-entrant: a caller that already opened a session simply joins it, so the
    processes are closed once, by whoever opened the outermost one.
    """
    SESSION.depth += 1
    try:
        yield
    finally:
        SESSION.depth -= 1
        if SESSION.depth == 0:
            close_session()


def close_session() -> None:
    """Close this thread's filter processes and forget its cached lookups."""
    processes, SESSION.processes = SESSION.processes, {}
    SESSION.commands = {}
    for process in processes.values():
        try:
            process.close()
        except Exception as error:  # noqa: BLE001 - shutdown is best effort
            taf_logger.debug("Could not close a git-lfs process: {}", error)


def process_for(executable: str, workdir: str) -> GitLFSProcess:
    """The filter process serving ``workdir`` in this thread.

    Reused for the length of a session, and created per call outside one, since
    nothing would otherwise close it.
    """
    if SESSION.depth == 0:
        return GitLFSProcess(executable, workdir)
    process = SESSION.processes.get(workdir)
    if process is None:
        process = GitLFSProcess(executable, workdir)
        SESSION.processes[workdir] = process
    return process
