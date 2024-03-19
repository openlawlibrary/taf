# Architecture Overview

This document describes a mental map of the `taf` repository. If you're starting to contribute to TAF, this might be the best first-place to look for.

TAF is a framework designed for validating, and securely cloning and updating Git repositories, utilizing The Update Framework (TUF). It does not directly improve Git's security or that of platforms such as GitHub, but aims to detect that an attack has occurred.

## Core concepts

A core concept in TAF is that of an authentication or TAF repository. This repository is a Git repository which at
every revision is also a valid TUF repository, containing metadata and target files in accordance with the TUF
specification. For more information about TUF, see its [official specification document](https://github.com/theupdateframework/specification/blob/master/tuf-spec.md).
The fact that it is a Git repository ensures that changes made to the metadata and target files and preserved over time.

This authentication repository contains information about other, regular Git repositories, which can contain any
arbitrary content. Most importantly, this information keeps track of valid commit SHAs of these repositories. In
order to update this information, a user needs to be in possession of specific signing keys, which are defined in
metadata files. If someone was to push to these referenced repositories, called target or data repositories,
without also updating TUF metadata and target files stored in the authentication repository, TAF's validation
would detect that change as invalid. There is a slight exception to these rules, since it can be defined that a
repository can contain unatuhenticated commits (not listed in authentication repository) between two authenticated
commits. However, if a repository only contains such commits, the secure clone/update processes will not download
anything.

An authentication repository can contain any target files, as defined by TUF, but is also expected to contain certain target files which have no special meaning in TUF, but do in TAF. These are:

* `repositories.json`: This file provides a list of the target (data) repositories.
* `dependencies.json`: This file contains details about other authentication repositories.
* `mirrors.json`: This file plays a role in determining the URLs used to download the repositories.
* `protected/info.json`: This file contains the authentication repository's metadata.
* `scripts` directory: Contains post-update hooks.

A user can use TAF's tools to set up and update authentication repositories, as well as its updater to run the
process of securely updating and cloning a set of repositories.

For an overview of updater, refer to [here](./updater.md), a more technical guide to update process is [here](./updater/update_process.md) (might be outdated as we change the CLI).

## Entry Point

The entry point to TAF are `taf` CLI commands implemented in [`click`](https://click.palletsprojects.com/), with top-level binding located in `taf/tools/cli/taf.py`.

## Code Map

### `docs`

The main source of TAF's technical documentation.

#### `docs/developers`

Contains documentation useful for developers building systems that include updating information stored in the authentication repositories. It includes a detailed overview of TAF's classes, which model the authentication repository, target repositories, and utilities for their instantiation.

#### `docs/devops`

A guide for building TAF wheels and setting up Azure pipelines.

#### `docs/testing`

A guide for creating test data. This section will be deprecated soon as we are looking to programmatically generate test data in our test setup.

#### `docs/updater`

Includes a thorough description of the update process and the relationship between TUF and TAF's updater.

#### `docs/user-guide`

Contains several documents meant to provide instructions on how to use TAF's tools for creating and updating authentication repositories, as well as the referenced target repositories.


### `specification`

 Contains a bird's-eye overview and a semi-technical introduction to TAF. It includes the TAF specification (`taf-spec.md`) and a `cross-repository-timestamp.md`. Work on Cross repository timestamp is currently in the early stages and this spec serves as an supplementary extension to the TAF spec.

### `whitepapers`

 Are the non-technical papers on digital archival, preservation and authentication in TAF. Currently has the original UELMA compliant whitepaper as the main motivation behind building taf.

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
