# Architecture Overview

This document describes a mental map of the `taf` repository. If you're starting to contribute to TAF, this might be the best first-place to look for.

TAF is a framework designed for validating, and securely cloning and updating Git repositories, utilizing The Update Framework (TUF). It does not directly improve Git's security or that of platforms such as GitHub, but aims to detect that an attack has occurred.

## Core concepts

A core concept in TAF is that of an authentication or TAF repository. This repository is a Git repository which at
every revision (alias for commit) is also a valid TUF repository, containing metadata and target files in accordance with the TUF
specification. For more information about TUF, see its [official specification document](https://github.com/theupdateframework/specification/blob/master/tuf-spec.md).
By using Git, we ensure that changes made to the metadata and target files and preserved over time.

This authentication repository contains information about other Git repositories (called target, or data repositories), which can contain any
arbitrary content. Most importantly, the authentication repository keeps track of valid commit SHAs of these repositories. In
order to update this information, a user needs to be in possession of specific signing keys. Currently, TAF supports keystores and hardware keys (YubiKeys). If a user wants to modify the state of the authentication repository, hardware key or keystore must be provided. TAF validates inserted/provided keys by comparing against public keys which are defined in
metadata files of the authentication repository. If someone wants to push to data repositories
without also updating TUF metadata and target files stored in the authentication repository, TAF's validation
would detect that change as invalid. Sometimes, users want to configure their authentication repository to skip validating all commits a data repository. This is solved by configuring that a
repository can contain unauthenticated commits (not listed in authentication repository) between two authenticated
commits.

An authentication repository can contain any target files, as defined by TUF, but is also expected to contain certain target files which have no special meaning in TUF, but do in TAF. These are:

* `repositories.json`: This file provides a list of the target (data) repositories.
* `dependencies.json`: This file contains details about other authentication repositories.
* `mirrors.json`: This file plays a role in determining the URLs used to download the repositories.
* `protected/info.json`: This file contains the authentication repository's metadata.
* `scripts` directory: Contains post-update hooks.

A user can use TAF's tools to set up and update authentication repositories, as well as the updater to run the
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

A guide for creating test data. We are moving away from manually creating git repositories for test fixtures. This section will be deprecated soon as we programmatically generate test data in our test setup.

#### `docs/updater`

Includes a thorough description of the update process and the relationship between TUF and TAF's updater.

#### `docs/user-guide`

Contains several documents meant to provide instructions on how to use TAF's tools for creating and updating authentication repositories, as well as the referenced target repositories.

### `specification`

 Contains a bird's-eye overview and a semi-technical introduction to TAF. It includes the TAF specification (`taf-spec.md`) and a `cross-repository-timestamp.md`. Work on Cross repository timestamp is currently in the early stages and this spec serves as an supplementary extension to the TAF spec.

### `whitepapers`

 Are the non-technical papers on digital archival, preservation and authentication in TAF. Currently has the original UELMA compliant whitepaper as the main motivation behind building taf.

### `taf/api`

Contains a collection of functions which are called by the `cli`, but can also be imported by other projects which use TAF. They include implementations of:

- Initial creation and setup of an authentication repository
- Setup, removal and update of TUF roles
- Signing TUF target files
- Update and signing of TUF metadata files
- Adding/removing new target repositories and dependencies (referenced authentication repositories)
-Ssetup of keystores and YubiKeys

### `taf/models`

Includes definitions of `attrs` classes, validators and converters. Long-term plan is to introduce types to all functions/signatures. Use types when writing any new
functions and methods.

For more information about `attrs`, see the [official documentation](https://www.attrs.org/en/stable/examples.html).

### `taf/tests`

The majority of the codebase is covered with tests, including APIs and the updater.

### `taf/tools`

This package includes a series of `click` CLI commands designed to interface directly with the API functions.

#### `taf/tools/dependencies`

Contains commands for adding and removing dependencies. This is done by updating `dependencies.json` and signing metadata files.

#### `taf/tools/keystore`

Used to generate new keystore files.

#### `taf/tools/metadata`

This module includes commands designed to manage expiration dates, offering functionalities for both checking and updating the expiration dates of metadata files.

### `taf/tools/repo`

Contains commands for creating a new authentication repository, as well as for validating, cloning, and updating repositories through TAF's updater.

### `taf/updater`

The process entails validating the authentication repository itself, through TUF's updater. A notable difference from
TUF is its focus on the latest version, disregarding intermediate versions. In contrast, TAF verifies every intermediate
version, requiring successive TUF updater invocations to incrementally update from version `n` to `n+1`, `n+2`, and so
on.

#### `taf/updater/updater.py`

This component has the top-level functions invoked by `cli` commands, including:

  - **clone**: Validates and clones repositories, intended for repositories not already on the filesystem.
  - **update**: Validates and updates local repositories, intended for repositories already present on the filesystem.
  - **validate**: Validates local repositories without altering disk contents.

These operations are directed at an authentication repository. Should this repository contain `dependencies.json`, the
clone/update/validate operations extend to each listed authentication repository. The primary workload is managed by a separate component, known as the pipeline. Post-pipeline execution, its outcomes are passed to lifecycle handlers, which trigger custom script execution. These handlers, located in a distinct module, are called after processing each authentication repository and after all dependencies have been handled.

#### `taf/updater/updater_pipeline.py`

Implemented as a sequence of functions, this module represents each step in the validation and update process of an
authentication repository and its referenced target repositories. It clones or updates or only validates repositories
depending on the command ran by CLI.

#### `taf/updater/lifecycle_handlers.py`

Authentication repositories can execute arbitrary scripts based on the clone/update's success or failure. Scripts, which may
return JSON containing both persistent and transient data, are executed in a specified sequence, receiving information
about the repository and update process. Persistent data is saved to the disk and passed along to subsequent scripts, while
transient data is only passed along. Scripts are not executed when only validating repositories.

#### `taf/updater/schemas.py`

This module includes JSON schemas that model data generated during the update process, which is then passed to the scripts.

### `taf/updater/handlers.py`

This module hosts the `GitUpdater` class, which extends TUF's `FetcherInterface`. It integrates TUF's updater with the git-based fetching of metadata files and targets without modifying TUF's validation processes. Since TUF's updater does not work with Git repositories, TAF adapts its `FetcherInterface`.

### `taf/updater/git_trusted_metadata_set.py`

To validate commits that could be decades old without being obstructed by expired metadata (TUF's default behavior), TAF extends `trusted_metadata_set.TrustedMetadataSet` with the `GitTrustedMetadataSet` class. This extension is implemented in a separate module named `git_trusted_metadata_set`, making it possible to validate older commits without expiration concerns.

### `taf/git.py`

This module encapsulates the `GitRepository` class, a high-level abstraction over Git operations, designed to interface directly with Git repositories at the filesystem level. The `GitRepository` class serves as an intermediary, enabling programmatic access to Git actions including: creating branches, working with commits, and working with remotes. It leverages [`pygit2`](https://www.pygit2.org/) for some of the interactions with Git. Other interactions use direct shell command execution via subprocess for operations not covered by `pygit2` or where direct command invocation is preferred for efficiency or functionality reasons.

### `taf/repository_tool.py`

Contains a `Repository` class, which is a wrapper around TUF's repository, making it simple to execute important updates, like
adding new signing keys, updating and signing metadata files and extracting information about roles, keys,
delegations and targets.

NOTE: Long-term plan is to rework this part of the codebase. This is necessary to transition to the newest version of TUF, since it is relying on parts which no longer exist in newer TUF.

### `taf/auth_repo.py`

This `AuthenticationRepository` class inherits from both `GitRepository` and `Repository`. Authentication repositories managed by this
class are expected to contain TUF metadata and target files.

### `taf/repositoriesdb.py`

The aim of this module is to load/instantiate target or referenced authentication repositories from an authentication repository. When instantiating, repositories are added to an in-memory "database" dictionary. This process reads from the contents of `repositories.json` and `targets.json` for target repositories, and `dependencies.json` for referenced authentication repositories.

### `taf/yubikey.py`

Features functionalities for configuring and utilizing YubiKeys for signature processes.

## Cross-cutting concerns

### Validity guarantees

Each command must ensure that all repositories remain in a valid state after execution. A repository is deemed
valid if all metadata is consistent and successfully validated by TAF, adhering to the following criteria at every
revision:

- The signatures of metadata files must be valid.
- Metadata files must conform to the TUF specification.
- Version numbers for metadata roles must increase by no more than +1 in each commit.
- Target files in the targets directory must be consistent with the information stored in metadata.
