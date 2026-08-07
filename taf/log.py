import os
import sys
import time
import logging
import zipfile
import datetime
from typing import Dict, Optional, TextIO, Union
from pathlib import Path

from loguru import logger as taf_logger
import taf.settings as settings

_CONSOLE_FORMAT_STRING = "\n{message}\n"
_FILE_FORMAT_STRING = "[{time}] [{level}] [{module}:{function}@{line}]\n{message}\n"

console_loggers: Dict = {}
file_loggers: Dict = {}

NOTICE = 25

# How long to stop retrying a failed rotation before trying again, in seconds.
# Without this, a single blocked rotation (see _RotatingFileSink) would otherwise
# be retried, and would fail again, on every subsequent log message.
_ROTATION_RETRY_COOLDOWN = 60


class _RotatingFileSink:
    """
    A loguru sink that rotates a log file by size, but tolerates the file being
    held open by another OS process.

    taf can be imported both by short-lived CLI subprocesses and by a long-running
    host process (e.g. an IDE extension's language server) that share the same
    log files on disk. On Windows, if one of those processes has the log file
    open, another process cannot rename it during rotation (WinError 32:
    "The process cannot access the file because it is being used by another
    process"). loguru's built-in rotation isn't resilient to that: the failed
    rename leaves its file handle closed, so the next write immediately retries
    the same rotation and fails the same way, flooding stderr with "Logging
    error" tracebacks for the remainder of the process's life.

    This sink instead treats a failed rotation as non-fatal: it keeps appending
    to the existing (temporarily oversized) file and only retries rotation after
    a short cooldown, instead of on every subsequent message.
    """

    def __init__(self, path, size_limit: int, retention: int, compression: bool):
        self._path = Path(path)
        self._size_limit = size_limit
        self._retention = retention
        self._compression = compression
        self._file: Optional[TextIO] = None
        self._rotation_retry_at: float = 0.0

    def _open(self):
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._file = open(self._path, "a", encoding="utf-8")

    def write(self, message):
        if self._file is None:
            self._open()

        if time.monotonic() >= self._rotation_retry_at:
            self._file.seek(0, os.SEEK_END)
            if self._file.tell() + len(message) > self._size_limit:
                if not self._rotate():
                    self._rotation_retry_at = (
                        time.monotonic() + _ROTATION_RETRY_COOLDOWN
                    )

        self._file.write(message)
        self._file.flush()

    def _rotate(self) -> bool:
        if self._file is not None:
            self._file.close()
            self._file = None

        renamed_path = self._generate_rename_path()
        try:
            os.rename(self._path, renamed_path)
        except OSError:
            # Most likely another process still has this file open. Give up on
            # rotating for now; keep appending to the existing file instead.
            self._open()
            return False

        if self._compression:
            self._compress(renamed_path)
        self._enforce_retention()

        self._open()
        return True

    def _generate_rename_path(self) -> Path:
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S_%f")
        stem, suffix = self._path.stem, self._path.suffix
        renamed_path = self._path.with_name(f"{stem}.{timestamp}{suffix}")
        counter = 1
        while renamed_path.exists():
            counter += 1
            renamed_path = self._path.with_name(f"{stem}.{timestamp}.{counter}{suffix}")
        return renamed_path

    def _compress(self, path: Path) -> None:
        zip_path = path.with_name(path.name + ".zip")
        try:
            with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
                zf.write(path, path.name)
            os.remove(path)
        except OSError:
            # Compression is best-effort; the rotated log is still preserved
            # uncompressed if this fails.
            pass

    def _enforce_retention(self) -> None:
        stem, suffix = self._path.stem, self._path.suffix
        try:
            logs = [
                log_path
                for log_path in self._path.parent.glob(f"{stem}.*{suffix}*")
                if log_path.is_file()
            ]
            logs.sort(key=lambda log_path: log_path.stat().st_mtime, reverse=True)
            for old_log in logs[self._retention :]:
                os.remove(old_log)
        except OSError:
            pass

    def stop(self) -> None:
        if self._file is not None:
            self._file.close()
            self._file = None


try:
    taf_logger.level("NOTICE", no=NOTICE, color="<yellow>", icon="!")
except (KeyError, ValueError):
    # If the level already exists, we can ignore this error.
    pass

VERBOSITY_LEVELS = {
    0: "NOTICE",  # Default
    1: "INFO",  # -v
    2: "DEBUG",  # -vv
    3: "TRACE",  # -vvv
}


def formatter(record):
    if record["level"].no == NOTICE:
        return f"<white>{_CONSOLE_FORMAT_STRING}</white>"
    elif record["level"].no == logging.WARNING:
        return f"<yellow>{_CONSOLE_FORMAT_STRING}</yellow>"
    elif record["level"].no == logging.INFO:
        return f"<blue>{_CONSOLE_FORMAT_STRING}</blue>"
    elif record["level"].no == logging.DEBUG:
        return f"<magenta>{_CONSOLE_FORMAT_STRING}</magenta>"
    elif record["level"].no == logging.ERROR:
        return f"<red>{_CONSOLE_FORMAT_STRING}</red>"
    else:
        return _CONSOLE_FORMAT_STRING


def disable_console_logging():
    try:
        taf_logger.remove(console_loggers["log"])
    except (KeyError, ValueError):
        # will be raised if this is called twice
        pass


def disable_file_logging():
    for handler_id in file_loggers:
        try:
            taf_logger.remove(file_loggers[handler_id])
        except (KeyError, ValueError):
            # will be raised if this is called twice
            pass


def _get_log_location():
    location = settings.LOGS_LOCATION or os.environ.get("TAF_LOG")
    if location is None:
        location = Path.home() / ".taf"
        location.mkdir(exist_ok=True)
    else:
        location = Path(location)
    return location


_ROTATION_SIZE_BYTES = 150 * 1024 * 1024
_RETENTION_COUNT = 5


def _add_file_logger(key: str, path: str, level) -> None:
    sink: Union[str, _RotatingFileSink]
    if settings.AUTO_ROTATE_LOGS:
        sink = _RotatingFileSink(
            path,
            size_limit=_ROTATION_SIZE_BYTES,
            retention=_RETENTION_COUNT,
            compression=True,
        )
    else:
        sink = path
    file_loggers[key] = taf_logger.add(sink, format=_FILE_FORMAT_STRING, level=level)


def initialize_logger_handlers():
    taf_logger.remove()
    if settings.ENABLE_CONSOLE_LOGGING:
        console_loggers["log"] = taf_logger.add(
            sys.stdout, format=formatter, level=VERBOSITY_LEVELS[settings.VERBOSITY]
        )

    if settings.ENABLE_FILE_LOGGING:
        log_location = _get_log_location()
        _add_file_logger(
            "log",
            str(log_location / settings.LOG_FILENAME),
            settings.FILE_LOGGING_LEVEL,
        )

        if settings.SEPARATE_ERRORS:
            _add_file_logger(
                "error",
                str(log_location / settings.ERROR_LOG_FILENAME),
                settings.ERROR_LOGGING_LEVEL,
            )

        _add_file_logger(
            "debug",
            str(log_location / settings.DEBUG_LOG_FILENAME),
            settings.DEBUG_LOGGING_LEVEL,
        )


initialize_logger_handlers()
