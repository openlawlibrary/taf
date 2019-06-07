
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
ENABLE_FILE_LOGGING = False

# If file logging is enabled via 'ENABLE_FILE_LOGGING', TAF log messages will
# be saved to 'LOG_FILENAME'
# not acutally implemented yet
LOG_FILENAME = 'taf.log'
