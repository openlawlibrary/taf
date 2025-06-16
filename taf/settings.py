import logging
import os

# Set a directory that should be used for all temporary files. If this
# is None, then the system default will be used. The system default
# will also be used if a directory path set here is invalid or
# unusable.
temporary_directory = None

conf_directory_root = None

update_from_filesystem = False

validate_repo_name = True

validation_repo_path: dict = {}

default_branch = None

# Strict mode enabled/disabled. If strict is enabled, any warnings
# should raise TAF errors
strict = False

# Allows usage of specified commit as last validated commit
# Useful when validating a local repository
overwrite_last_validated_commit = False

last_validated_commit: dict = {}

# determines if script files will be loaded from disk
development_mode = False

# determines if lifecycle handler scripts will be run
run_scripts = False

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

DEBUG_LOGGING_LEVEL = logging.DEBUG

# If True, the log files will be rotated automatically when they reach a certain size.
AUTO_ROTATE_LOGS = os.environ.get("TAF_AUTO_ROTATE_LOGS", "1").lower() in (
    "1",
    "true",
    "yes",
)

# Location of the log files. It can be specified by setting LOGS_LOCATION
# and by setting an environment variable called TAF_LOG.
# If this location is not specified logs will be placed ~/.taf
LOGS_LOCATION = None

LOG_FILENAME = "taf.log"

ERROR_LOG_FILENAME = "taf.err"

DEBUG_LOG_FILENAME = "taf-debug.log"

LOG_COMMAND_OUTPUT = False

VERBOSITY = 0
