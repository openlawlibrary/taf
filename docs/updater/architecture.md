# Updater Architecture Overview

## `updater`

This component encompasses the top-level functions invoked by `cli` commands, including:
  - **clone**: Validates and clones repositories, intended for repositories not already on the filesystem.
  - **update**: Validates and updates local repositories, intended for repositories already present on the filesystem.
  - **validate**: Validates local repositories without altering disk contents.

These operations are directed at an authentication repository. Should this repository contain `dependencies.json`, the 
clone/update/validate operations extend to each listed authentication repository. The primary workload is managed by a separate component, known as the pipeline. Post-pipeline execution, its outcomes are passed to lifecycle handlers, which trigger custom script execution. These handlers, located in a distinct module, are called after processing each authentication repository and after all dependencies have been handled.

## `updater_pipeline`

Implemented as a sequence of functions, this module represents each step in the validation and update process of an 
authentication repository and its referenced target repositories. It clones or updates or only validates repositories 
based on the given operation. The pipeline offers multiple benefits:
- It manages state as a pipeline class attribute, allowing for efficient state sharing among functions. This method is simpler and more intuitive than variable passing.
- The workflow is straightforward, with easy inclusion or exclusion of steps.
- It is simple to include/exclude steps depending on the operation.

The process entails validating the authentication repository itself, through TUF's updater. A notable difference from 
TUF is its focus on the latest version, disregarding intermediate versions. In contrast, TAF verifies every intermediate 
version, requiring successive TUF updater invocations to incrementally update from version `n` to `n+1`, `n+2`, and so 
on.

Since TUF's updater does not work with Git repositories, TAF adapts its `FetcherInterface`.


## `handlers` and `git_trusted_metadata_set` Module


This module hosts the `GitUpdater` class, which extends TUF's `FetcherInterface`. It integrates TUF's updater with the git-based fetching of metadata files and targets without modifying TUF's validation processes.

To validate commits that could be decades old without being obstructed by expired metadata (TUF's default behavior), TAF extends `trusted_metadata_set.TrustedMetadataSet` with the `GitTrustedMetadataSet` class. This extension is implemented in a separate module named `git_trusted_metadata_set`, making it possible to validate older commits without expiration concerns.


## `lifecycle_handlers`

Authentication repositories can execute Python scripts based on the clone/update's success or failure. Scripts, which may 
return JSON containing both persistent and transient data, are executed in a specified sequence, receiving information 
about the repository and update process. Persistent data is saved and passed along to subsequent scripts, while 
transient data is only passed along. Scripts are not executed when only validating repositories.
Execution of these scripts is handled by the `lifecycle_handlers` module.
