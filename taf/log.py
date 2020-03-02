import os
import sys
import tuf.log
from loguru import logger as taf_logger
from pathlib import Path
import taf.settings as settings

_FORMAT_STRING = "[{time}] [{level}] [{module} {function}@{line}]\n{message}\n"

console_loggers = {}
file_loggers = {}


def _get_log_location():
    location = settings.LOGS_LOCATION or os.environ.get("TAF_LOG")
    if location is None:
        location = Path.home() / ".taf"
        location.mkdir(exist_ok=True)
    else:
        location = Path(location)
    return location


taf_logger.remove()

if settings.ENABLE_CONSOLE_LOGGING:
    console_loggers["log"] = taf_logger.add(
        sys.stdout, format=_FORMAT_STRING, level=settings.CONSOLE_LOGGING_LEVEL
    )
    console_loggers["error"] = taf_logger.add(
        sys.stderr, format=_FORMAT_STRING, level=settings.ERROR_LOGGING_LEVEL
    )


if settings.ENABLE_FILE_LOGGING:
    logs_location = _get_log_location()
    log_path = str(logs_location / settings.LOG_FILENAME)
    file_loggers["log"] = taf_logger.add(
        log_path, format=_FORMAT_STRING, level=settings.FILE_LOGGING_LEVEL
    )

    if settings.SEPARATE_ERRORS:
        error_log_path = str(logs_location / settings.ERROR_LOG_FILENAME)
        file_loggers["error"] = taf_logger.add(
            error_log_path, format=_FORMAT_STRING, level=settings.ERROR_LOGGING_LEVEL
        )


def disable_console_logging(remove_error=False):
    taf_logger.remove(console_loggers["log"])
    if remove_error:
        taf_logger.remove(console_loggers["error"])
    tuf.log.remove_console_handler()
