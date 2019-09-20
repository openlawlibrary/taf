import logging
from pathlib import Path

import taf.settings

_FORMAT_STRING = '[%(asctime)s] [%(levelname)s] ' + \
    '[%(funcName)s:%(lineno)s@%(filename)s]\n%(message)s\n'
formatter = logging.Formatter(_FORMAT_STRING)

logger = logging.getLogger('taf')
logger.setLevel(taf.settings.LOG_LEVEL)



if taf.settings.ENABLE_CONSOLE_LOGGING:
  console_handler = logging.StreamHandler()
  console_handler.setLevel(taf.settings.CONSOLE_LOGGING_LEVEL)
  console_handler.setFormatter(formatter)
  logger.addHandler(console_handler)


if taf.settings.ENABLE_FILE_LOGGING:
  logs_location = taf.settings.LOGS_LOCATION
  if logs_location is None:
    logs_location = Path('/var/log')
    if not logs_location.is_dir():
      logs_location = Path.home() / '.taf'
      logs_location.mkdir(exist_ok=True)
  else:
    logs_location = Path(logs_location)
  file_handler = logging.FileHandler(str(logs_location / taf.settings.LOG_FILENAME))
  file_handler.setLevel(taf.settings.FILE_LOGGING_LEVEL)
  file_handler.setFormatter(formatter)
  logger.addHandler(file_handler)

  if taf.settings.SEPARATE_ERRORS:
    error_handler = logging.FileHandler(str(logs_location / taf.settings.ERROR_LOG_FILENAME))
    error_handler.setLevel(taf.settings.ERROR_LOGGING_LEVEL)
    error_handler.setFormatter(formatter)
    logger.addHandler(error_handler)


def get_logger(name):
  return logging.getLogger(name)
