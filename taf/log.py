import os
import sys
import logging
from typing import Dict
import securesystemslib
from pathlib import Path

import tuf.log
import tuf.repository_tool
import tuf.exceptions
from loguru import logger as taf_logger
import taf.settings as settings

_CONSOLE_FORMAT_STRING = "\n{message}\n"
_FILE_FORMAT_STRING = "[{time}] [{level}] [{module}:{function}@{line}]\n{message}\n"

console_loggers: Dict = {}
file_loggers: Dict = {}

NOTICE = 25
taf_logger.level("NOTICE", no=NOTICE, color="<yellow>", icon="!")

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
        disable_tuf_console_logging()
    except ValueError:
        # will be raised if this is called twice
        pass


def disable_file_logging():
    try:
        taf_logger.remove(file_loggers["log"])
        disable_tuf_console_logging()
    except ValueError:
        # will be raised if this is called twice
        pass


def disable_tuf_console_logging():
    try:
        tuf.log.set_console_log_level(logging.CRITICAL)
    except securesystemslib.exceptions.Error:
        pass


def disable_tuf_file_logging():
    if tuf.log.file_handler is not None:
        tuf.log.disable_file_logging()
    else:
        logging.getLogger("tuf").setLevel(logging.CRITICAL)
    logging.getLogger("securesystemslib_keys").setLevel(logging.CRITICAL)
    logging.getLogger("securesystemslib_util").setLevel(logging.CRITICAL)


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
        tuf.log.set_console_log_level(logging.ERROR)
    else:
        # if console logging is disable, remove tuf console logger
        disable_tuf_console_logging()

    if settings.ENABLE_FILE_LOGGING:
        log_location = _get_log_location()
        log_path = str(log_location / settings.LOG_FILENAME)
        file_loggers["log"] = taf_logger.add(
            log_path, format=_FILE_FORMAT_STRING, level=settings.FILE_LOGGING_LEVEL
        )

        if settings.SEPARATE_ERRORS:
            error_log_path = str(log_location / settings.ERROR_LOG_FILENAME)
            file_loggers["error"] = taf_logger.add(
                error_log_path,
                format=_FILE_FORMAT_STRING,
                level=settings.ERROR_LOGGING_LEVEL,
            )
        try:
            tuf.log.set_filehandler_log_level(settings.FILE_LOGGING_LEVEL)
        except tuf.exceptions.Error:
            pass
    else:
        # if file logging is disabled, also disable tuf file logging
        disable_tuf_file_logging()


initialize_logger_handlers()
