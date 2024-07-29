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

# JMC: Add NOTICE logging level
NOTICE = 25
logging.addLevelName(25, "NOTICE")

def notice(self, message, *args, **kws):
    taf_logger.log("NOTICE", message, *args, **kws)
    taf_logger.notice = notice()

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

# JMC: Verbosity Additions
VERBOSITY_LEVELS = {
    1: NOTICE,
    2: logging.INFO,
    3: logging.DEBUG
}

#taf_logger = logging.getLogger("taf")

def set_logging(verbosity):
    log_level = VERBOSITY_LEVELS.get(verbosity, logging.WARNING)
    taf_logger.remove()
    taf_logger.add(sys.stderr, level=log_level, format="{time} - {name} - {level} - {message}")
    logs_location = _get_log_location()
    taf_logger.add(logs_location / "taf.log", level=log_level, format="{time} - {name} - {level} - {message}")


    '''taf_logger.setLevel(VERBOSITY_LEVELS.get(verbosity, logging.WARNING))
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    taf_logger.addHandler(console_handler)

    logs_location = _get_log_location()
    global file_handler
    file_handler = logging.FileHandler(logs_location / "taf.log")
    file_handler.setFormatter(formatter)
    taf_logger.addHandler(file_handler)'''

taf_logger.remove()

if settings.ENABLE_CONSOLE_LOGGING:
    console_loggers["log"] = taf_logger.add(
        sys.stdout, format=_CONSOLE_FORMAT_STRING, level=settings.CONSOLE_LOGGING_LEVEL
    )
    tuf.log.set_console_log_level(settings.CONSOLE_LOGGING_LEVEL)
else:
    # if console logging is disable, remove tuf console logger
    disable_tuf_console_logging()


if settings.ENABLE_FILE_LOGGING:
    logs_location = _get_log_location()
    log_path = str(logs_location / settings.LOG_FILENAME)
    file_loggers["log"] = taf_logger.add(
        log_path, format=_FILE_FORMAT_STRING, level=settings.FILE_LOGGING_LEVEL
    )

    if settings.SEPARATE_ERRORS:
        error_log_path = str(logs_location / settings.ERROR_LOG_FILENAME)
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
