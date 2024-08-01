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
from logging import handlers
import taf.settings as settings

_CONSOLE_FORMAT_STRING = "\n{message}\n"
_FILE_FORMAT_STRING = "[{time}] [{level}] [{module}:{function}@{line}]\n{message}\n"

console_loggers: Dict = {}
file_loggers: Dict = {}

# JMC: Add NOTICE logging level
NOTICE = 25
taf_logger.level("NOTICE", no=NOTICE, color="<yellow>", icon="!")
#taf_logger.log("NOTICE", "Validation repository {repo}: cloning repository...")

def notice(self, message, *args, **kwargs):
    if self.isEnabledFor(NOTICE):
        self._log("NOTICE", message, args, **kwargs)
#taf_logger.__class__.notice = notice
taf_logger.notice = notice

def disable_file_logging():
    try:
        for handler_id in taf_logger._core.handlers.copy():
            handler = taf_logger._core.handlers[handler_id]
            if handler.sink != sys.stderr:
                taf_logger.remove(handler_id)
        #taf_logger.remove(console_loggers["log"])
        disable_tuf_console_logging()
    except ValueError:
        # will be raised if this is called twice
        pass

def disable_file_logging():
    try:
        for handler_id in taf_logger._core.handlers.copy():
            handler = taf_logger._core.handlers[handler_id]
            if handler.sink != sys.stderr:
                taf_logger.remove(handler_id)
        #taf_logger.remove(file_loggers["log"])
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
    1: "NOTICE",
    2: "INFO",
    3: "DEBUG"
}

def set_logging(verbosity):
    #log_level = VERBOSITY_LEVELS.get(verbosity, "WARNING")
    #log_format = "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>"

    #taf_logger.remove()
    # Remove all handlers associated with the logger object.
    '''for handler in taf_logger.handlers:
        print(f"Handler: {handler.__class__.__name__}, Level: {logging.getLevelName(handler.level)}")
'''

    taf_logger.remove()
    taf_logger.add(sys.stderr, level=VERBOSITY_LEVELS.get(verbosity, "WARNING"))

    log_location = _get_log_location()
    taf_logger.add(log_location / "taf.log", level=VERBOSITY_LEVELS.get(verbosity, "WARNING"))

    # Add console handler
    #taf_logger.add(sys.stderr, level=log_level, format=log_format)

    # Add file handler
    #log_location = _get_log_location()
    #taf_logger.add(str(log_location / "taf.log"), level=log_level, format=log_format)

    '''taf_logger.remove()
    log_level = VERBOSITY_LEVELS.get(verbosity, "WARNING")
    log_format = log_format = "{time} - {name} - {level} - {message}"
    #taf_logger.add(sys.stderr, level=VERBOSITY_LEVELS.get(verbosity, "WARNING"))

    taf_logger.add(sys.stderr, level=log_level, format=log_format)

    # Add file handler
    log_location = _get_log_location()
    taf_logger.add(str(log_location / "taf.log"), level=log_level, format=log_format)
'''
def get_taf_logger():
    return taf_logger

if settings.ENABLE_CONSOLE_LOGGING:
    console_loggers["log"] = taf_logger.add(
        sys.stdout, format=_CONSOLE_FORMAT_STRING, level=settings.CONSOLE_LOGGING_LEVEL
    )
    tuf.log.set_console_log_level(settings.CONSOLE_LOGGING_LEVEL)
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
