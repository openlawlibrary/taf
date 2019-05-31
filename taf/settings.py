
import logging

# Set a directory that should be used for all temporary files. If this
# is None, then the system default will be used. The system default
# will also be used if a directory path set here is invalid or
# unusable.
temporary_directory = None

update_from_filesystem = False


LOG_LEVEL = logging.DEBUG

# wheter to log to the console, which does not mean that file logging can be enabled as well
ENABLE_CONSOLE_LOGGING = True

# wheter to log to a file, which does not mean that console logging can be enabled as well
ENABLE_FILE_LOGGING = False

# if logging to file is enabled, should errors be logged to a separate file
SEPARATE_ERRORS = False

CONSOLE_LOGGING_LEVEL = logging.DEBUG

FILE_LOGGING_LEVEL = logging.INFO

ERROR_LOGGING_LEVEL = logging.WARNING

LOG_FILENAME = 'taf.log'

ERROR_LOF_FILENAME = 'taf.err'
