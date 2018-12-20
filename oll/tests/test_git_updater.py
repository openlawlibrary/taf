# We need to implement tests for our updater. We do not need to re-implement the whole
# TUF's test_updater', because we only slightly modify the process. We need to check
# if the git repositories were updated, if the appropriate exception was raised.
# Some of the things we need address and test include:
# - successful update, when the users repository was several commits behind the remote one
# - error when someone force pushed to the remote repository and removed a number of commits
# so that the client's top commit is ahead of the one in the remote repository
# - successful update when one or more intermediate commits contain expired metadata
# - error when a metadata file shouldn't have had change, but that is not the case.