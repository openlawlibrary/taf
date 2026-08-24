"""A long-running ``git-lfs filter-process`` per repository.

git starts one filter process for a whole operation and reuses it for every
file. Starting one per file instead costs about a process launch per file,
which on an archive of a hundred thousand documents is most of the checkout.

Content is streamed both ways and staged before it is handed on, so nothing
is held whole in memory and nothing partial is emitted: a stream that is
abandoned mid-file would otherwise leave a truncated working-tree file, and
libgit2 offers no way to abort.
"""

import subprocess
import threading
from tempfile import SpooledTemporaryFile
from typing import IO, Dict, List, Optional, Tuple

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


class GitLFSProcessError(Exception):
    """The filter process could not be started, or stopped responding."""


class GitLFSProcess:
    """One ``git-lfs filter-process``, driven over pkt-line.

    Not thread-safe on its own; ``GitLFSProcessPool`` hands each caller an
    instance no one else holds.
    """

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
            process.wait(timeout=10)
        except (OSError, subprocess.SubprocessError):
            process.kill()

    def filter(self, verb: str, path: str, source: IO[bytes]) -> IO[bytes]:
        """Run ``verb`` over ``source``; return a rewound stream of the result.

        Raises ``GitLFSProcessError`` if git-lfs reports failure or the
        connection breaks, leaving the caller free to fall back - nothing has
        been emitted at that point.
        """
        process = self._ensure_started()
        if process.stdin is None or process.stdout is None:
            raise GitLFSProcessError("git-lfs was started without pipes")
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
            staged: IO[bytes] = SpooledTemporaryFile(max_size=SPOOL_LIMIT)  # type: ignore[assignment]
            # packet by packet: collecting the section first would hold the
            # whole file in memory, which is what the staging exists to avoid
            for packet in iter(lambda: read_packet(stdout), None):
                staged.write(packet)
            self._expect_success(read_text_section(stdout), verb, path)
        except (EOFError, OSError, ValueError) as error:
            self.close()
            raise GitLFSProcessError(
                f"git-lfs {verb} of '{path}' failed: {error}"
            ) from error
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
            raise GitLFSProcessError(f"git-lfs did not start: {error}") from error
        self._process = process
        return process

    @staticmethod
    def _expect_success(status: List[str], verb: str, path: str) -> None:
        if "status=success" not in status:
            raise GitLFSProcessError(
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


class GitLFSProcessPool:
    """Keeps one filter process per repository, per concurrent caller.

    The updater materializes target repositories through a thread pool, and a
    pkt-line connection carries one exchange at a time, so callers are handed
    an instance nobody else holds and return it when done.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._idle: Dict[Tuple[str, str], list] = {}

    def acquire(self, executable: str, workdir: str) -> GitLFSProcess:
        key = (executable, workdir)
        with self._lock:
            pooled = self._idle.get(key)
            if pooled:
                return pooled.pop()
        return GitLFSProcess(executable, workdir)

    def release(self, process: GitLFSProcess) -> None:
        key = (process.executable, process.workdir)
        with self._lock:
            self._idle.setdefault(key, []).append(process)

    def close_all(self) -> None:
        with self._lock:
            pooled, self._idle = self._idle, {}
        for processes in pooled.values():
            for process in processes:
                try:
                    process.close()
                except Exception as error:  # noqa: BLE001 - shutdown is best effort
                    taf_logger.debug("Could not close a git-lfs process: {}", error)


POOL = GitLFSProcessPool()
