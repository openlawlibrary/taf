import os
import sys
import logging
from typing import Dict
from pathlib import Path

from loguru import logger as taf_logger
import taf.settings as settings

_CONSOLE_FORMAT_STRING = "\n{message}\n"
_FILE_FORMAT_STRING = "[{time}] [{level}] [{module}:{function}@{line}]\n{message}\n"

console_loggers: Dict = {}
file_loggers: Dict = {}

NOTICE = 25

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
    try:
        taf_logger.remove(file_loggers["log"])
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


def initialize_logger_handlers():
    taf_logger.remove()
    if settings.ENABLE_CONSOLE_LOGGING:
        console_loggers["log"] = taf_logger.add(
            sys.stdout, format=formatter, level=VERBOSITY_LEVELS[settings.VERBOSITY]
        )

    if settings.ENABLE_FILE_LOGGING:
        log_location = _get_log_location()
        log_path = str(log_location / settings.LOG_FILENAME)
        if settings.AUTO_ROTATE_LOGS:
            file_loggers["log"] = taf_logger.add(
                log_path,
                format=_FILE_FORMAT_STRING,
                level=settings.FILE_LOGGING_LEVEL,
                rotation="150 MB",
                retention=5,
                compression="zip",
            )
        else:
            file_loggers["log"] = taf_logger.add(
                log_path,
                format=_FILE_FORMAT_STRING,
                level=settings.FILE_LOGGING_LEVEL,
            )

        if settings.SEPARATE_ERRORS:
            error_log_path = str(log_location / settings.ERROR_LOG_FILENAME)
            if settings.AUTO_ROTATE_LOGS:
                file_loggers["error"] = taf_logger.add(
                    error_log_path,
                    format=_FILE_FORMAT_STRING,
                    level=settings.ERROR_LOGGING_LEVEL,
                    rotation="150 MB",
                    retention=5,
                    compression="zip",
                )
            else:
                file_loggers["error"] = taf_logger.add(
                    error_log_path,
                    format=_FILE_FORMAT_STRING,
                    level=settings.ERROR_LOGGING_LEVEL,
                )
        debug_log_path = str(log_location / settings.DEBUG_LOG_FILENAME)
        if settings.AUTO_ROTATE_LOGS:
            file_loggers["debug"] = taf_logger.add(
                debug_log_path,
                format=_FILE_FORMAT_STRING,
                level=settings.DEBUG_LOGGING_LEVEL,
                rotation="150 MB",
                retention=5,
                compression="zip",
            )
        else:
            file_loggers["debug"] = taf_logger.add(
                debug_log_path,
                format=_FILE_FORMAT_STRING,
                level=settings.DEBUG_LOGGING_LEVEL,
            )


initialize_logger_handlers()
