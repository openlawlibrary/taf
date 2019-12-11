import os
import sys
from loguru import logger as taf_logger
from pathlib import Path

import taf.settings

_FORMAT_STRING = "[{time}] [{level}] [{module} {function}@{line}]\n{message}\n"


def _get_log_location():
    location = taf.settings.LOGS_LOCATION or os.environ.get("TAF_LOG")
    if location is None:
        location = Path.home() / ".taf"
        location.mkdir(exist_ok=True)
    else:
        location = Path(location)
    return location


taf_logger.remove()

if taf.settings.ENABLE_CONSOLE_LOGGING:
    taf_logger.add(
        sys.stdout, format=_FORMAT_STRING, level=taf.settings.CONSOLE_LOGGING_LEVEL
    )
    taf_logger.add(
        sys.stderr, format=_FORMAT_STRING, level=taf.settings.ERROR_LOGGING_LEVEL
    )


if taf.settings.ENABLE_FILE_LOGGING:
    logs_location = _get_log_location()
    log_path = str(logs_location / taf.settings.LOG_FILENAME)
    taf_logger.add(
        log_path, format=_FORMAT_STRING, level=taf.settings.FILE_LOGGING_LEVEL
    )

    if taf.settings.SEPARATE_ERRORS:
        error_log_path = str(logs_location / taf.settings.ERROR_LOG_FILENAME)
        taf_logger.add(
            error_log_path,
            format=_FORMAT_STRING,
            level=taf.settings.ERROR_LOGGING_LEVEL,
        )
