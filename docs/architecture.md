# Architecture Overview

This document describes a mental map of the `taf` repository. If you're starting to contribute to taf, this might be the best first-place to look for.

For an overview of updater, refer to [here](./updater.md), a more technical guide to update process is [here](./updater/update_process.md) (might be outdated as we change the CLI).

## Entry Point

The entrypoint to TAF are `taf` CLI commands implemented in [`click`](https://click.palletsprojects.com/), with top-level binding located in `taf/tools/cli/taf.py`.

## Code Map

### `docs`

 Is the main source of taf technical documentation.

### `docs/developers`, `docs/updater`

 Contains more specific development documentation, such as devops related steps, the classes used to instantiate git repositories and the updater workflow.

### `specification`

 Contains a birds-eye overview and a semi-technical introduction to TAF. It contains the TAF specification (`taf-spec.md`) and a `cross-repository-timestamp.md`. Work on Cross repository timestamp is currently in early stages and this spec serves as an supplementary extension to the TAF spec.

### `whitepapers`

 Are the non-technical papers on digital archival, preservation and authentication in TAF. Currently has the original UELMA compliant whitepaper as the main reason for building taf.

### `taf/api`

### `taf/models`

### `taf/tests`

### `taf/tools`

### `taf/tools/dependencies`

### `taf/tools/keystore`

### `taf/tools/metadata`

### `taf/tools/repo`

### `taf/updater`

The process entails validating the authentication repository itself, through TUF's updater. A notable difference from
TUF is its focus on the latest version, disregarding intermediate versions. In contrast, TAF verifies every intermediate
version, requiring successive TUF updater invocations to incrementally update from version `n` to `n+1`, `n+2`, and so
on.

### `taf/updater/updater.py`

This component has the top-level functions invoked by `cli` commands, including:

  - **clone**: Validates and clones repositories, intended for repositories not already on the filesystem.
  - **update**: Validates and updates local repositories, intended for repositories already present on the filesystem.
  - **validate**: Validates local repositories without altering disk contents.

These operations are directed at an authentication repository. Should this repository contain `dependencies.json`, the
clone/update/validate operations extend to each listed authentication repository. The primary workload is managed by a separate component, known as the pipeline. Post-pipeline execution, its outcomes are passed to lifecycle handlers, which trigger custom script execution. These handlers, located in a distinct module, are called after processing each authentication repository and after all dependencies have been handled.

### `taf/updater/updater_pipeline.py`

Implemented as a sequence of functions, this module represents each step in the validation and update process of an
authentication repository and its referenced target repositories. It clones or updates or only validates repositories
based on the given operation.

### `taf/updater/schemas.py`

### `taf/updater/lifecycle_handlers.py`

Authentication repositories can execute arbitrary scripts based on the clone/update's success or failure. Scripts, which may
return JSON containing both persistent and transient data, are executed in a specified sequence, receiving information
about the repository and update process. Persistent data is saved to the disk and passed along to subsequent scripts, while
transient data is only passed along. Scripts are not executed when only validating repositories.

### `taf/updater/handlers.py`

This module hosts the `GitUpdater` class, which extends TUF's `FetcherInterface`. It integrates TUF's updater with the git-based fetching of metadata files and targets without modifying TUF's validation processes. Since TUF's updater does not work with Git repositories, TAF adapts its `FetcherInterface`.

### `taf/updater/git_trusted_metadata_set.py`

To validate commits that could be decades old without being obstructed by expired metadata (TUF's default behavior), TAF extends `trusted_metadata_set.TrustedMetadataSet` with the `GitTrustedMetadataSet` class. This extension is implemented in a separate module named `git_trusted_metadata_set`, making it possible to validate older commits without expiration concerns.

### `taf/updater/types`

## TAF core modules

### `taf/auth_repo.py`

### `taf/git.py`

### `taf/repository_tool.py`

### `taf/repositoriesdb.py`

### `taf/yubikey.py`

## Cross-cutting concerns

### Validity guarantees

  Each command needs to leave the all repositories in a valid state. A repository is considered valid when all metadata is consistent and can be validated using `taf` successfully.

  This means that, at each revision:

   - Signatures of metadata files are valid.
   - Metadata files are valid according to TUF specification.
   - Version numbers for `metadata` roles in each commit need to increase by, at most, `+ 1`.
   - Target files in `targets` directory are valid according to data stored in metadata.
