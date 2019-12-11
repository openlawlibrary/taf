import logging

# Set a directory that should be used for all temporary files. If this
# is None, then the system default will be used. The system default
# will also be used if a directory path set here is invalid or
# unusable.
temporary_directory = None

update_from_filesystem = False

validate_repo_name = True

# The 'log.py' module manages TUF's logging system.  Users have the option to
# enable/disable logging to a file via 'ENABLE_FILE_LOGGING', or
# tuf.log.enable_file_logging() and tuf.log.disable_file_logging().


# whether to log to the console, which does not mean that file logging cannot be enabled as well
ENABLE_CONSOLE_LOGGING = True

# whether to log to a file, which does not mean that console logging cannot be enabled as well
ENABLE_FILE_LOGGING = True

# should errors be logged to a separate file if logging to file is enabled
SEPARATE_ERRORS = True

CONSOLE_LOGGING_LEVEL = logging.INFO

FILE_LOGGING_LEVEL = logging.INFO

ERROR_LOGGING_LEVEL = logging.WARNING

# Location of the log files. It can be specified by setting LOGS_LOCATION
# and by setting an environment variable called TAF_LOG.
# If this location is not specified logs will be placed ~/.taf
LOGS_LOCATION = None

LOG_FILENAME = "taf.log"

ERROR_LOG_FILENAME = "taf.err"

LOG_COMMAND_OUTPUT = False
