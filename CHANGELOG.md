# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog][keepachangelog],
and this project adheres to [Semantic Versioning][semver].


## [0.35.0a1] - 03/17/2025

### Added

- Implement get all auth repos logic ([599])
- Add Commitish model ([596])
- Aadd tests for part of the git module ([596])
- Add a command for setting names of keys ([594])
- Add an option to specify names of keys using an external file ([594])
- Implement adaptive timeout for Git clone operations ([592])
- Check if repository is synced with remote before running API functions ([592])
- Add key names from config files to metadata during repository setup, following updates to TUF and securesystemslib ([583])
- Implement iteration over all inserted YubiKeys during metadata signing ([583])
- Implement a `PinManager` class to allow secure pin reuse across API functions and eliminated insecure global pin storage ([583])

### Changed

- Re-implement restore without using a feature not available in older versions of git ([592])

### Fixed

- Optionally include yubikey cli group. Ensures that CLI can be used without ykman ([604])
- Fix setting names of keys when not stored in metadata files ([603])
- Ensure that every target role has a delegations attribute [(595)]
- Fix wrong default branch assignment for target repos [(593)]


[604]: https://github.com/openlawlibrary/taf/pull/604
[603]: https://github.com/openlawlibrary/taf/pull/603
[599]: https://github.com/openlawlibrary/taf/pull/599
[596]: https://github.com/openlawlibrary/taf/pull/596
[595]: https://github.com/openlawlibrary/taf/pull/595
[594]: https://github.com/openlawlibrary/taf/pull/594
[593]: https://github.com/openlawlibrary/taf/pull/593
[592]: https://github.com/openlawlibrary/taf/pull/592
[583]: https://github.com/openlawlibrary/taf/pull/583

## [0.34.1] - 02/11/2025

### Added

- Improved Git error messaging to provide clearer troubleshooting instructions for remote operations ([588])

### Changed


### Fixed

- Fixed loading from repositories cache ([590])

[590]: https://github.com/openlawlibrary/taf/pull/590
[588]: https://github.com/openlawlibrary/taf/pull/588


## [0.34.0] - 02/04/2025

### Added

- Added benchmark testing for test_clone_valid_happy_path ([584])
- Implement removal and rotation of keys ([561])

### Changed

- Transition to the newest version of TUF ([561])

### Fixed

[584]: https://github.com/openlawlibrary/taf/pull/584
[561]: https://github.com/openlawlibrary/taf/pull/561

## [0.33.2] - 02/04/2025

### Added

### Changed

### Fixed

- Fix `_is_repository_in_sync` check ([585])

[585]: https://github.com/openlawlibrary/taf/pull/585


## [0.33.1] - 01/09/2025

### Added

### Changed

### Fixed

- Run validation with --no-deps when pushing ([579])
- Do not update last validated commit if pushing to a branch other than the default branch ([577])
- Fix determining from which commit the update should start if the auth repo is in front of all target repos ([577])

[579]: https://github.com/openlawlibrary/taf/pull/579
[577]: https://github.com/openlawlibrary/taf/pull/577


## [0.33.0] - 12/23/2024

### Added

- Add tests for `get_last_remote_commit` and `reset_to_commit` ([573])
- Remove unused optional parameter from _yk_piv_ctrl ([572])
- Implement full partial update. Store last validated commit per repo ([559]))

### Changed

### Fixed

[573]: https://github.com/openlawlibrary/taf/pull/573
[572]: https://github.com/openlawlibrary/taf/pull/572
[559]: https://github.com/openlawlibrary/taf/pull/559


## [0.32.4] - 12/03/2024

### Added

### Changed

- Change log level for `repositoriesdb` messages ([569])

### Fixed

[569]: https://github.com/openlawlibrary/taf/pull/569

## [0.32.3] - 11/22/2024

### Added

### Changed

### Fixed

- Fix `get_last_remote_commit` - add missing value for parameter ([566])

[566]: https://github.com/openlawlibrary/taf/pull/566

## [0.32.2] - 11/20/2024

### Added

### Changed

- Make url optional for `get_last_remote_commit` ([564])

### Fixed

[564]: https://github.com/openlawlibrary/taf/pull/564

## [0.32.1] - 11/01/2024

### Added

### Changed

### Fixed

- Fix two git methods where `GitError` was not being instantiated correctly ([562])
- Fix determination of auth commits to be validated when starting the update from the beginning ([562])

[562]: https://github.com/openlawlibrary/taf/pull/562

## [0.32.0] - 10/23/2024

### Added


### Changed


### Fixed

- Fix specification of pygit2 version depending on the Python version ([558])
- Fix validation and listing targets of an auth repo that does not contain `mirrors.json` ([558])

[558]: https://github.com/openlawlibrary/taf/pull/558


## [0.31.2] - 10/16/2024

### Added

- Added a function for exporting `keys-description.json` ([550])
- Added support for cloning a new dependency when adding it to `dependencies.json` if it is not on disk ([550])
- Clean up authentication repository if an error occurs while running a cli command ([550])

### Changed

- Return a non-zero exit code with `sys.exit` when updater fails ([550])
- Rework addition of a new role and target repositories. Use `custom.json` files ([550])


### Fixed

- Minor `conf init` and detection of the authentication repository fixes ([550])
- Replace `info` logging calls with `notice` in API functions ([550])
- Use `mirrors.json` urls when cloning dependencies ([551])


[551]: https://github.com/openlawlibrary/taf/pull/551
[550]: https://github.com/openlawlibrary/taf/pull/550


## [0.31.1] - 10/03/2024

### Added

### Changed

### Fixed

- Fix `load_repositories` following a rework needed to support parallelization ([547])
- Fix `clone_from_disk` ([547])
- Fix pre-push hook ([547])

[547]: https://github.com/openlawlibrary/taf/pull/547


## [0.31.0] - 09/28/2024

### Added


- Added lxml to taf pyinstaller to execute arbitrary python scripts ([535])
- Added support for execution of executable files within the scripts directories ([529])
- Added yubikey_present parameter to keys description (Can be specified when generating keys) ([508])
- Removed 2048-bit key restriction [494]
- Allow for the displaying of varied levels of log and debug information based on the verbosity level ([493])
- Added new tests to test out of sync repositories and manual updates ([488], [504])
- Update when auth repo's top commit is behind last validated commit [490]
- Added lazy loading to CLI [481]
- Testing repositories with dependencies ([479], [487])
- Hid plaintext when users are prompted to insert YubiKey and press ENTER ([473])
- Added functionality for parallel execution of child repo during clone and update for performance enhancement ([472])
- New flag --force allowing forced updates ([471])
- Improved usability (TAF finds the repo if current directory has no repo, create a .taf directory to manage keys) ([466])
- Added git hook check for updater ([460])
- New flag --no-deps allowing users to only update the current repository and not update dependent repositories from dependencies.json ([455], [463])
- New flag --no-targets allowing users to skip target repository validation when validating the authentication repo ([455])
- New flag --no-upstream allowing users to skip upstream comparisons ([455], [463])
- Addition of logic to tuples (steps) and the run function in updater_pipeline.py to determine which steps, if any, will be skipped based on the usage of 
  the --no-targets flag ([455])
- Added --bare tags for repository cloning and updating ([459])
- Added workflow to build standalone executable of TAF ([447])

### Changed

- If in detached head state or an older branch, do not automatically checkout the newest one without force ([543])
- Move validation of the last validated commit to the pipeline from the update handler ([543])
- Default verbosity to 0 (NOTICE) level; add notice level update outcome logging ([538])
- Raise a more descriptive error if `pygit2` repository cannot be instantiated  ([485], [489])
- Enhanced commit_and_push for better error logging and update the last validated commit ([469])
- Generate public key from private key if .pub file is missing ([462])
- Port release workflow from Azure Pipelines to GitHub Actions ([458])
- Remove platform-specific builds, do not package DLLs which are no longer necessary ([458])

### Fixed

- Handle invalid last validated commit ([543])
- Fixes to executing taf handler scripts from a pyinstaller executable ([535])
- Fix `persisent` and `transient` NoneType error when running taf handlers ([535])
- Fix update status when a target repo was updated and the auth repo was not ([532])
- Fix merge-commit which wasn't updating the remote-tracking branch ([532])
- Fix removal of additional local commits ([532])
- Fix top-level authentication repository update to correctly update child auth repos ([528])
- Fix setup role when specifying public keys in keys-description ([511])
- `check_if_repositories_clean` error now returns a list of repositories which aren't clean, instead of a single repository ([525])


[543]: https://github.com/openlawlibrary/taf/pull/543
[538]: https://github.com/openlawlibrary/taf/pull/538
[535]: https://github.com/openlawlibrary/taf/pull/535
[532]: https://github.com/openlawlibrary/taf/pull/532
[529]: https://github.com/openlawlibrary/taf/pull/529
[528]: https://github.com/openlawlibrary/taf/pull/528
[525]: https://github.com/openlawlibrary/taf/pull/525
[511]: https://github.com/openlawlibrary/taf/pull/511
[508]: https://github.com/openlawlibrary/taf/pull/508
[504]: https://github.com/openlawlibrary/taf/pull/504
[494]: https://github.com/openlawlibrary/taf/pull/494
[493]: https://github.com/openlawlibrary/taf/pull/493
[490]: https://github.com/openlawlibrary/taf/pull/490
[489]: https://github.com/openlawlibrary/taf/pull/489
[488]: https://github.com/openlawlibrary/taf/pull/488
[487]: https://github.com/openlawlibrary/taf/pull/487
[485]: https://github.com/openlawlibrary/taf/pull/485
[481]: https://github.com/openlawlibrary/taf/pull/481
[479]: https://github.com/openlawlibrary/taf/pull/479
[473]: https://github.com/openlawlibrary/taf/pull/473
[472]: https://github.com/openlawlibrary/taf/pull/472
[471]: https://github.com/openlawlibrary/taf/pull/471
[469]: https://github.com/openlawlibrary/taf/pull/469
[466]: https://github.com/openlawlibrary/taf/pull/466
[463]: https://github.com/openlawlibrary/taf/pull/463
[462]: https://github.com/openlawlibrary/taf/pull/462
[460]: https://github.com/openlawlibrary/taf/pull/460
[459]: https://github.com/openlawlibrary/taf/pull/459
[458]: https://github.com/openlawlibrary/taf/pull/458
[455]: https://github.com/openlawlibrary/taf/pull/455
[447]: https://github.com/openlawlibrary/taf/pull/447


## [0.29.2] - 07/04/2024


### Added

- Use git remote show if symbolic-ref fails for default_branch ([457])
- Add a command for adding delegated paths to a role ([391])
- Check if metadata files at revision match those downloaded by TUF updater ([389])

### Changed

### Fixed
- Checking git repos existence and changing imprecise and undescriptive error messages accordingly 

- Fix `clone_or_pull` ([402])

[457]: https://github.com/openlawlibrary/taf/pull/457
[402]: https://github.com/openlawlibrary/taf/pull/402
[391]: https://github.com/openlawlibrary/taf/pull/391
[389]: https://github.com/openlawlibrary/taf/pull/389

## [0.30.3] - 08/29/2024

### Added

### Changed

### Fixed

- Move `yubikey_utils` module to include it in wheel ([516])

[516]: https://github.com/openlawlibrary/taf/pull/516

## [0.30.2] - 08/20/2024

### Added

- New flag --no-deps allowing users to only update the current repository and not update dependent repositories from dependencies.json ([455])
- New flag --no-targets allowing users to skip target repository validation when validating the authentication repo ([455])
- New flag --no-upstream allowing users to skip upstream comparisons ([455])

- Addition of logic to tuples (steps) and the run function in updater_pipeline.py to determine which steps, if any, will be skipped based on the usage of 
  the --no-targets flag ([455])

### Changed

### Fixed

[463]: https://github.com/openlawlibrary/taf/pull/463
[455]: https://github.com/openlawlibrary/taf/pull/455

## [0.30.1] - 07/23/2024

### Added

- Add info.json data loading ([476])

### Changed

### Fixed

- Build: use correct `sys.version_info` comparison when installing `pygit2` ([470])
- Validate branch can be modified with check branch length function ([470])

[476]: https://github.com/openlawlibrary/taf/pull/476
[470]: https://github.com/openlawlibrary/taf/pull/470


## [0.30.0] - 06/12/2024


### Added

- Support for Yubikey Manager 5.1.x ([444])
- Support for Python 3.11 and 3.12 ([440])
- Fix add_target_repo when signing role is the top-level targets role ([431])
- New git hook that validates repo before push ([423])
- New function taf repo status that prints the state of whole library ([422])
- New function taf roles list that lists all roles in an authentication repository ([421])
- Clone target repositories to temp ([412], [418])
- Add architecture overview documentation ([405])
- Add a command for adding delegated paths to a role ([391])
- Check if metadata files at revision match those downloaded by TUF updater ([389])

### Changed

- Updater testing framework rework [453]
- Update pytest version [453]
- Drop support for Python 3.7 [453]
- Dropped support for Yubikey Manager 4.x [444]
- Only load the latest mirrors.jon ([441])
- Fix generation of keys when they should be printed to the command line ([435])
- Made Updater faster through parallelization ([434])
- Reimplemented get_file_details function to not rely on old securesystemslib functions ([420])
- Check if repositories are clean before running the updater ([416])
- Only show merging commits messages if actually merging commits. Rework logic for checking if a commits should be merged ([404], [415])

### Fixed

- Fix YubiKey setup ([445])
- Fixes repeating error messages in taf repo create and manual entry of keys-description ([432])
- When checking if branch is synced, find first remote that works, instead of only trying the last remote url ([419])
- Disable check if metadata files at revision match ([403])
- Fix `clone_or_pull` ([402])

[453]: https://github.com/openlawlibrary/taf/pull/453
[445]: https://github.com/openlawlibrary/taf/pull/445
[444]: https://github.com/openlawlibrary/taf/pull/444
[440]: https://github.com/openlawlibrary/taf/pull/440
[435]: https://github.com/openlawlibrary/taf/pull/435
[434]: https://github.com/openlawlibrary/taf/pull/434
[432]: https://github.com/openlawlibrary/taf/pull/432
[431]: https://github.com/openlawlibrary/taf/pull/431
[423]: https://github.com/openlawlibrary/taf/pull/423
[422]: https://github.com/openlawlibrary/taf/pull/422
[421]: https://github.com/openlawlibrary/taf/pull/421
[420]: https://github.com/openlawlibrary/taf/pull/420
[419]: https://github.com/openlawlibrary/taf/pull/419
[418]: https://github.com/openlawlibrary/taf/pull/418
[416]: https://github.com/openlawlibrary/taf/pull/416
[415]: https://github.com/openlawlibrary/taf/pull/415
[412]: https://github.com/openlawlibrary/taf/pull/412
[405]: https://github.com/openlawlibrary/taf/pull/405
[404]: https://github.com/openlawlibrary/taf/pull/404
[403]: https://github.com/openlawlibrary/taf/pull/403
[402]: https://github.com/openlawlibrary/taf/pull/402
[391]: https://github.com/openlawlibrary/taf/pull/391
[389]: https://github.com/openlawlibrary/taf/pull/389


## [0.29.1] - 02/07/2024

### Added

- Add a test for updating a repositories which references other authentication repositories. Test repositories are set up programmatically ([386])

### Changed

- Update find_first_branch_matching_pattern return - only return name of the found branch and not all branches whose name did not match the pattern ([387])

### Fixed

- Validation of local repositories should not fail if there are no local branches (e.g. after a fresh clone) ([387])
- Fix GitError exception instantiations ([387])
- -Fix a minor bug where update status was incorrectly being set in case when a repository with only one commit is cloned ([386])

[387]: https://github.com/openlawlibrary/taf/pull/387
[386]: https://github.com/openlawlibrary/taf/pull/386


## [0.29.0] - 01/24/2024

### Added

- Print a warning if the conf file cannot be loaded when executing scripts ([384])
- Git: added a method for finding the newest branch whose name matches a certain pattern ([375])
- Git: added a check if remote already exists ([375])

### Changed

- Only clone repositories if target files exists ([381])
- Do not merge unauthenticated commits which are newer than the last authenticated commit if a repository can contain unauthenticated commits ([381])
- Partially update authentication repositories up to the last valid commit ([381])
- Check if there are uncommitted changes when running the updater ([377])
- Implement updater pipeline ([374])
- Improve error messages and error logging ([374])
- Update target repositories in a breadth-first way ([374])

### Fixed

- Fix update of repositories which reference other repositories ([384])
- Fix imports, do not require installation of yubikey-manager prior to running the update ([376])
- Git: fix the commit method so that it raises an error if nothing is committed ([375])

[381]: https://github.com/openlawlibrary/taf/pull/381
[377]: https://github.com/openlawlibrary/taf/pull/377
[376]: https://github.com/openlawlibrary/taf/pull/376
[375]: https://github.com/openlawlibrary/taf/pull/375
[374]: https://github.com/openlawlibrary/taf/pull/374

## [0.28.0] - 11/10/2023

### Added

- Implement tests for the functions which are directly called by the cli (API package) ([362])
- Add push flag to all functions that used to always automatically push to remote in order to be able to prevent that behavior ([362])
- Add a command for listing all roles (including delegated paths if applicable) whose metadata the inserted YubiKey can sign ([362])
- Added mypy static type checking to pre-commit hook ([360])

### Changed

- Docs: update readme, add acknowledgements ([365])
- Move add/remove dependencies to a separate module ([362])
- Move all API helper functions to separate modules ([362])
- Fixed errors reported by mypy ([360])

### Fixed

- Fix loading of keys and create repo when old yubikey flag is used ([370])
- Fix keys naming issue after adding a new signing key to a role that only had one signing key ([362])
- Fix removal of targets when removing a role ([362])

[370]: https://github.com/openlawlibrary/taf/pull/370
[365]: https://github.com/openlawlibrary/taf/pull/365
[362]: https://github.com/openlawlibrary/taf/pull/362
[360]: https://github.com/openlawlibrary/taf/pull/360

## [0.27.0] - 09/22/2023

### Added

- Automatically commit and push to remote unless a --no-commit flag is specified ([357])
- Adding typing information to api functions and the git module ([357])
- List keys of roles with additional information read from certificates command ([355])
- Export certificate from the inserted YubiKey ([355])
- Add signing keys given a public key when creating a new authentication repository ([354])
- Allow specification of names of YubiKeys in repository description json ([354])
- Model repository description json input using `attrs` and `cattrs` and its validation ([354])
- Add test for repo initialization when it is directly inside drive's root ([352])
- Add functions for adding/updating/removing dependencies to/from dependencies.json ([338])

### Changed

- Split tests into separate packages ([353])
- Minor add/remove target repository improvements ([351])
- Bump `cattrs` ([349])
- Improve CLI error handling ([346])
- Update signing keys loading. Add a flag for specifying if the user will be asked to manually enter a key ([346])
- Remove default branch specification from updater ([343])
- Updater: only load repositories defined in the newest version of repositories.json ([341])
- Updater: automatically determine url if local repository exists ([340])
- Remove hosts and hosts.json ([330])

### Fixed

- Fix list targets in case when the target repo is not up to date with remote ([357])
- Fix repositories.json update when adding new target repository ([351])
- Fix error when keystore path is not provided ([351])
- Make it possible to execute commands that don't require yubikey without installing yubikey-manager ([342])
- Fix commits per repositories function when same target commits are on different branches ([337])
- Add missing `write` flag to `taf targets sign` ([329])

[357]: https://github.com/openlawlibrary/taf/pull/357
[355]: https://github.com/openlawlibrary/taf/pull/355
[354]: https://github.com/openlawlibrary/taf/pull/354
[352]: https://github.com/openlawlibrary/taf/pull/352
[349]: https://github.com/openlawlibrary/taf/pull/349
[346]: https://github.com/openlawlibrary/taf/pull/346
[343]: https://github.com/openlawlibrary/taf/pull/343
[342]: https://github.com/openlawlibrary/taf/pull/342
[341]: https://github.com/openlawlibrary/taf/pull/341
[340]: https://github.com/openlawlibrary/taf/pull/340
[338]: https://github.com/openlawlibrary/taf/pull/338
[337]: https://github.com/openlawlibrary/taf/pull/337
[330]: https://github.com/openlawlibrary/taf/pull/330
[329]: https://github.com/openlawlibrary/taf/pull/329

## [0.26.1] - 08/29/2023

### Added

### Changed

- Bump `cattrs` ([349])

### Fixed


## [0.26.0] - 07/12/2023

### Added

- Add command for adding/removing roles ([314])

### Changed

- Docstirngs logging improvements ([325])
- Keystore path in roles_key_info calculated relative to where the json file is ([321])
- Try to sign using a yubikey before asking the user if they want to use a yubikey ([320])
- Split `developer_tool` into separate modules ([314], [321])

### Fixed

- Fix create repository ([325])

[325]: https://github.com/openlawlibrary/taf/pull/325
[321]: https://github.com/openlawlibrary/taf/pull/321
[320]: https://github.com/openlawlibrary/taf/pull/320
[314]: https://github.com/openlawlibrary/taf/pull/314

## [0.25.0] - 03/31/2023

### Added

### Changed

- Update license, release under agpl ([313])

### Fixed

- Fix execution of scripts ([311])

[313]: https://github.com/openlawlibrary/taf/pull/313
[311]: https://github.com/openlawlibrary/taf/pull/311

## [0.24.0] - 02/21/2023

### Added

- Add git methods for adding an remove remotes and check if merge conflicts occurred ([309])
- Add a command for updating and signing targets of specified typed ([308])

### Changed

### Fixed

- Use `generate_and_write_unencrypted_rsa_keypair` for no provided password ([305])

[309]: https://github.com/openlawlibrary/taf/pull/309
[308]: https://github.com/openlawlibrary/taf/pull/308
[305]: https://github.com/openlawlibrary/taf/pull/305

## [0.23.1] - 01/13/2023

### Added

### Changed

### Fixed

- Fix `clone_or_pull` method ([303])

[303]: https://github.com/openlawlibrary/taf/pull/303

## [0.23.0] - 12/27/2022

### Added

- Auto-detect default branch ([300])

### Changed

### Fixed

- Remove pytest11 default entrypoint ([301])

[301]: https://github.com/openlawlibrary/taf/pull/301
[300]: https://github.com/openlawlibrary/taf/pull/300

## [0.22.4] - 12/15/2022

### Added

### Changed

### Fixed

- Pin `pyOpenSSL` to newer version ([299])

[299]: https://github.com/openlawlibrary/taf/pull/299

## [0.22.3] - 12/14/2022

### Added

### Changed

### Fixed

- Add missing tuf import in `log.py` ([298])

[298]: https://github.com/openlawlibrary/taf/pull/298

## [0.22.2] - 12/14/2022

### Added

### Changed

### Fixed

- Remove _tuf_patches in `__init__.py` ([297])

[297]: https://github.com/openlawlibrary/taf/pull/297

### Added

### Changed

### Fixed

## [0.22.1] - 12/14/2022

### Added

### Changed

### Fixed

- Move _tuf_patches to repository lib ([296])

[296]: https://github.com/openlawlibrary/taf/pull/296

## [0.22.0] - 12/09/2022

### Added

### Changed

- Support first commits on branches with a missing branch file ([292])
- Upgrade cryptography version ([279])
- Turn expired metadata into a warning instead of an error by default ([275])
- Upgraded our TUF fork to newer version ([273])

### Fixed

- Pin securesystemslib and cryptography ([294])
- Use `is_test_repo` AuthRepository property in updater ([293])
- Remove leftover git worktree code in error handling ([291])
- Fix `get_role_repositories` to find common roles in both `repositories.json` and metadata ([286])
- Replace buggy `all_fetched_commits` with `all_commits_on_branch` ([285])
- Fix pygit2 performance regression ([283])
- Fix `taf metadata update-expiration-date --role snapshot` to include `root` ([282])
- Fix `all_commits_since_commit` to validate provided commit ([278])
- Remove pin for `PyOpenSSL` ([273])
- Fix `all_commits_since_commit` to validate provided commit ([278])
- Remove pin for `PyOpenSSL` ([273])

[294]: https://github.com/openlawlibrary/taf/pull/294
[293]: https://github.com/openlawlibrary/taf/pull/293
[292]: https://github.com/openlawlibrary/taf/pull/292
[291]: https://github.com/openlawlibrary/taf/pull/291
[286]: https://github.com/openlawlibrary/taf/pull/286
[285]: https://github.com/openlawlibrary/taf/pull/285
[283]: https://github.com/openlawlibrary/taf/pull/283
[282]: https://github.com/openlawlibrary/taf/pull/282
[279]: https://github.com/openlawlibrary/taf/pull/279
[278]: https://github.com/openlawlibrary/taf/pull/278
[275]: https://github.com/openlawlibrary/taf/pull/275
[273]: https://github.com/openlawlibrary/taf/pull/273

## [0.21.1] - 09/07/2022

### Added

### Changed

### Fixed

- Extended `top_commit_of_branch`, support references which are not branches, like HEAD ([270])
- Add pygit_repo error handling and fix couple of `git.py` logs ([269])

[270]: https://github.com/openlawlibrary/taf/pull/270
[269]: https://github.com/openlawlibrary/taf/pull/269

## [0.21.0] - 08/30/2022

### Added

- Add support for multiple branch and capstone files ([266])
- Add cli metadata command that checks if metadata roles are soon to expire ([261])
- Document a solution to a YubiKey communication issue ([257])

### Changed

- If target role expiration date is being updated, sign timestamp and snapshot automatically ([261])
- `--clients-auth-path` repo command improvements ([260])
- port a number of git functionalities to pygit2 ([227])
- Migrated yubikey-manager from v3.0.0 to v4.0.\* ([191])

### Fixed

- Do not remove authentication repository folder when running `taf repo validate` ([267])
- fix git push - remove pygit2 push implementation which does not fully support ssh ([263])
- Warn when git object cleanup fails (`idx`,`pack`) and include cleanup warning message ([259])

[267]: https://github.com/openlawlibrary/taf/pull/267
[266]: https://github.com/openlawlibrary/taf/pull/266
[263]: https://github.com/openlawlibrary/taf/pull/263
[261]: https://github.com/openlawlibrary/taf/pull/261
[260]: https://github.com/openlawlibrary/taf/pull/260
[259]: https://github.com/openlawlibrary/taf/pull/259
[257]: https://github.com/openlawlibrary/taf/pull/257
[227]: https://github.com/openlawlibrary/taf/pull/227
[191]: https://github.com/openlawlibrary/taf/pull/191

## [0.20.0] - 06/22/2022

### Added

### Changed

- Remove Python 3.6 support ([256])
- Remove pinned pynacl which is incompatible with Python 3.10 ([256])

### Fixed

[256]: https://github.com/openlawlibrary/taf/pull/256

## [0.19.0] - 06/14/2022

### Added

### Changed

- Loosen dependencies and pin pynacl ([254])

### Fixed

[254]: https://github.com/openlawlibrary/taf/pull/254

## [0.18.0] - 05/31/2022

### Added

- Add support for Python 3.10 ([247])

### Changed

- Enable exclusion of certain target repositories from the update process ([250])
- Update `_get_unchanged_targets_metadata` - `updated_roles` is now a list ([246])

### Fixed

- Fix `validate_branch` indentation error caused by [246] ([249])

[250]: https://github.com/openlawlibrary/taf/pull/250
[249]: https://github.com/openlawlibrary/taf/pull/249
[247]: https://github.com/openlawlibrary/taf/pull/247
[246]: https://github.com/openlawlibrary/taf/pull/246

## [0.17.0] - 05/04/2022

### Added

- Add auth commit to sorted_commits_and_branches_per_repositories ([240])
- Add --version option to cli ([239])
- Add TAF's repository classes and repositoriesdb's documentation ([237])
- Add `--ff-only` to git merge ([235])
- Added format-output flag to update repo cli ([234])
- Cache loaded git files ([228])
- Add a flag for generating performance reports of update calls and print total update execution time ([228])

### Changed

- Update `targets_at_revisions` - only update a list of roles if a metadata file was added ([228])

### Fixed

[240]: https://github.com/openlawlibrary/taf/pull/240
[239]: https://github.com/openlawlibrary/taf/pull/239
[237]: https://github.com/openlawlibrary/taf/pull/237
[235]: https://github.com/openlawlibrary/taf/pull/235
[234]: https://github.com/openlawlibrary/taf/pull/234
[228]: https://github.com/openlawlibrary/taf/pull/228

## [0.16.0] - 04/16/2022

### Added

- Add `allow_unsafe` flag to git repo class as a response to a recent git security fix ([229])

### Changed

- Remove `no_checkout=True` from `clone` ([226])
- Remove `--error-if-unauthenticated` flag ([220])
- Change `clients-auth-path` in `taf repo update` to optional. ([213])
- Only clone if directory is empty ([211])

### Fixed

- Fix updates of repos which only contain one commit ([219])
- Fixed `_validate_urls` and local validation ([216])

[229]: https://github.com/openlawlibrary/taf/pull/229
[226]: https://github.com/openlawlibrary/taf/pull/226
[220]: https://github.com/openlawlibrary/taf/pull/220
[219]: https://github.com/openlawlibrary/taf/pull/219
[216]: https://github.com/openlawlibrary/taf/pull/216
[213]: https://github.com/openlawlibrary/taf/pull/213
[211]: https://github.com/openlawlibrary/taf/pull/211

## [0.15.0] - 02/11/2022

### Added

- Docs: add `info.json` example ([236])
- `Update` handler pipeline, showcase mapping dict fields to class types with `attrs` + `cattrs`. ([206])
- Schema for update handler. ([206])
- Add `type` tests for `attrs` structuring. ([206])

### Changed

### Fixed

- perf: re-implementing slow git cmds with pygit2 ([207])
- Specify a list of repositories which shouldn't contain additional commits instead of just specifying a flag ([203])

### Fixed

- Update handler fix: return an empty list of targets if the targets folder does not exist ([208])
- pytest works when taf installed via wheel ([200])

[236]: https://github.com/openlawlibrary/taf/pull/236
[208]: https://github.com/openlawlibrary/taf/pull/208
[207]: https://github.com/openlawlibrary/taf/pull/207
[206]: https://github.com/openlawlibrary/taf/pull/206
[200]: https://github.com/openlawlibrary/taf/pull/200

## [0.14.0] - 01/25/2022

### Added

### Changed

- Specify a list of repositories which shouldn't contain additional commits instead of just specifying a flag ([203])

### Fixed

- Raise an error if a repository which should not contain additional commits does so ([203])
- Do not merge target commits if update as a whole will later fail ([203])

[203]: https://github.com/openlawlibrary/taf/pull/203

## [0.13.4] - 01/20/2022

### Added

### Changed

- Trim text read from the last_validated_commit file ([201])

### Fixed

[201]: https://github.com/openlawlibrary/taf/pull/201

## [0.13.3] - 11/18/2021

### Added

### Changed

- Update create local branch git command - remove checkout ([197])
- Iterate throuh all urls when checking if a local repo is synced with remote ([197])

### Fixed

[197]: https://github.com/openlawlibrary/taf/pull/197

## [0.13.2] - 11/11/2021

### Added

### Changed

- Remove commit checkout and checkout the latest branch for each target repository ([195])
- If top commit of the authentication repository is not the same as the `last_validated_commit`, validate the newer commits as if they were just pulled ([195])

### Fixed

[195]: https://github.com/openlawlibrary/taf/pull/195

## [0.13.1] - 10/22/2021

### Added

### Changed

### Fixed

- Pass default branch to sorted_commits_and_branches_per_repositories ([185])

[185]: https://github.com/openlawlibrary/taf/pull/185

## [0.13.0] - 10/20/2021

### Added

### Changed

- Pin cryptography and pyOpenSSL versions to keep compatibility with yubikey-manager 3.0.0 ([184])

### Fixed

[184]: https://github.com/openlawlibrary/taf/pull/184

## [0.12.0] - 10/18/2021

### Added

### Changed

- Updated cryptography version ([183])

### Fixed

- Fix validate local repo command ([183])

[183]: https://github.com/openlawlibrary/taf/pull/183

## [0.11.2] - 09/29/2021

### Added

### Changed

- Exclude test date from wheels ([182])

### Fixed

[182]: https://github.com/openlawlibrary/taf/pull/182

## [0.11.1] - 09/29/2021

### Added

### Changed

- Removed generate schema docs due to their long names causing issues on Windows when installing taf ([181])

### Fixed

[181]: https://github.com/openlawlibrary/taf/pull/181

## [0.11.0] - 09/28/2021

### Added

- Added support for skipping automatic checkout ([179])

### Changed

- Compare current head commit according to the auth repo and top commit of target repo and raise an error if they are different ([179])

### Fixed

- Automatically remove current and previous directories if they exist before instantiating tuf repo ([179])
- Fixed branch exists check. Avoid wrongly returning true if there is a warning ([179])
- Fixed update of repos which can contain unauhtenticated commits - combine fetched and existing commits ([179])
- Fixed handling of additional commits on a branch ([179])

[179]: https://github.com/openlawlibrary/taf/pull/179

## [0.10.1] - 08/16/2021

### Added

### Changed

- Do not raise an error if the hosts file is missing ([177])

### Fixed

[177]: https://github.com/openlawlibrary/taf/pull/177

## [0.10.0] - 07/20/2021

### Added

### Changed

- Update click to 7.1 ([176])

### Fixed

## [0.9.0] - 06/30/2021

### Added

- Initial support for executing handlers. Handlers are scripts contained by auth repos which can be used to execute some code after successful/failed update of a repository and/or a host. ([164])
- Implemented delegation of auth repositories - an auth repository can reference others by defining a special target file `dependencies.json`. Updater will pull all referenced repositories. ([164])
- Provided a way of specifying hosts of repositories though a special target file called `hosts.json` ([164])
- Verification of the initial commit of a repository given `out-of-band-authentication` commit either directly passed into the udater or stored in `dependencies.json` of the parent auth repo. ([164])

### Changed

- Renamed `repo_name` and `repo_urls` attributes to `name` and `urls` and `additional_info` to `custom` ([164])
- Reworked repository classes ([164])
- Transition from TravisCI to Github Actions ([173])

### Fixed

[176]: https://github.com/openlawlibrary/taf/pull/176
[173]: https://github.com/openlawlibrary/taf/pull/173
[164]: https://github.com/openlawlibrary/taf/pull/164

## [0.8.1] - 04/14/2021

### Added

- Added a command for checking validity of the inserted YubiKey's pin ([165])
- Raise an error if there are additional commits newer than the last authenticated commit if the updater is called with the check-authenticated flag ([161])
- Added initial worktrees support to the updater ([161])
- Added support for specifying location of the conf directory ([161])
- Added a function for disabling fie logging ([161])

### Changed

- Raise keystore error when key not found in keystore directory [166]
- Replaced authenticate-test-repo flag with an enum ([161])

### Fixed

- Minor validation command fix ([161])

[166]: https://github.com/openlawlibrary/taf/pull/166
[165]: https://github.com/openlawlibrary/taf/pull/165
[161]: https://github.com/openlawlibrary/taf/pull/161

## [0.8.0] - 02/09/2021

### Added

### Changed

- Pin cryptography version ([162])

### Fixed

[162]: https://github.com/openlawlibrary/taf/pull/162

## [0.7.2] - 11/11/2020

### Added

- Add a command for adding new new delegated roles ([158])

### Changed

### Fixed

[158]: https://github.com/openlawlibrary/taf/pull/158

## [0.7.1] - 10/28/2020

### Added

### Changed

- Small branches_containing_commit git method fix following git changes ([156])

### Fixed

[156]: https://github.com/openlawlibrary/taf/pull/156

## [0.7.0] - 10/16/2020

### Added

- Add support for fully disabling tuf logging ([154])
- Add support for including additional custom information when exporting historical data ([147])

### Changed

- Store authentication repo's path as key in `repositoriesdb` instead of its name ([153])

### Fixed

- Minor YubiKey mock fix ([153])
- Updated some git methods so that it is checked if the returned value is not `None` before calling strip ([153])

[154]: https://github.com/openlawlibrary/taf/pull/154
[153]: https://github.com/openlawlibrary/taf/pull/153
[147]: https://github.com/openlawlibrary/taf/pull/147

## [0.6.1] - 09/09/2020

### Added

- Get binary file from git (skip encoding) ([148])

### Changed

### Fixed

[148]: https://github.com/openlawlibrary/taf/pull/148

## [0.6.0] - 08/11/2020

### Added

- Git method for getting the first commit on a branch ([145])

### Changed

- Minor check capstone validation update ([145])
- Check if specified target repositories exist before trying to export historical commits data ([144])

### Fixed

[145]: https://github.com/openlawlibrary/taf/pull/145
[144]: https://github.com/openlawlibrary/taf/pull/144

## [0.5.2] - 07/21/2020

### Added

- Git method for removing remote tracking branches ([142])

### Changed

- Check remote repository when checking if a branch already exists ([142])

### Fixed

[142]: https://github.com/openlawlibrary/taf/pull/142

## [0.5.1] - 06/25/2020

### Added

### Changed

- Documentation updates ([140])
- Set `only_load_targets` parameter to `True` by default in `repositoriesdb` ([139])
- Use `_load_signing_keys` in `add_signing_key` ([138])
- Raise a nicer error when instantiating a TUF repository if it is invalid ([137])

### Fixed

- Fix loading targets metadata files in `repositoriesdb` ([139])

[140]: https://github.com/openlawlibrary/taf/pull/140
[139]: https://github.com/openlawlibrary/taf/pull/139
[138]: https://github.com/openlawlibrary/taf/pull/138
[137]: https://github.com/openlawlibrary/taf/pull/137

## [0.5.0] - 06/04/2020

### Added

- Add `repositoriesdb` tests ([134])
- Add support for defining urls using a separate `mirrors.json` file ([134])
- Add a command for exporting targets historical data ([133])

### Changed

- Updated `repositoriesdb` so that delegated target roles are taken into considerations when finding targets data ([134])
- `sorted_commits_and_branches_per_repositories` returns additional targets data and not just commits ([133])

### Fixed

[134]: https://github.com/openlawlibrary/taf/pull/134
[133]: https://github.com/openlawlibrary/taf/pull/133

## [0.4.1] - 05/12/2020

### Added

### Changed

- Error handling and logging improvements ([131])

### Fixed

[131]: https://github.com/openlawlibrary/taf/pull/131

## [0.4.0] - 05/01/2020

### Added

- Git method to create orphan branch ([129])
- Added updater check which verifies that metadata corresponding to the last commit has not yet expired ([124])
- Additional updater tests ([124])
- Added command for validating repositories without updating them ([124])
- Import error handling for `taf.yubikey` module ([120])
- Updater tests which validate updated root metadata ([118])
- New test cases for updating targets/delegations metadata ([116])
- Create empty targets directory before instantiating tuf repository if it does not exist ([114])
- When creating a new repository, print user's answers to setup question as json ([114])
- Sign all target files which are found inside the targets directory when creating a new repository ([114])

### Changed

- Minor logging updates ([126])
- Updater: Partial repo factory ([125])
- Logging formats ([120])
- Use common role of given targets during update of targets/delegations metadata ([116])
- Changed format of keys description json, as it can now contain roles' description under "roles" key and keystore path under "keystore" key ([114])

### Fixed

- Import errors (ykman) inside tests ([129])
- Fixed addition of new signing key so that this functionality works in case of delegated roles ([128])
- Fixed synced_with_remote ([121])
- Signing fixes with keystore keys ([120])
- Load signing keys minor fixes ([120] [117])
- Normalize target files when creating a new repository ([117])

[129]: https://github.com/openlawlibrary/taf/pull/129
[128]: https://github.com/openlawlibrary/taf/pull/128
[126]: https://github.com/openlawlibrary/taf/pull/126
[125]: https://github.com/openlawlibrary/taf/pull/125
[124]: https://github.com/openlawlibrary/taf/pull/124
[121]: https://github.com/openlawlibrary/taf/pull/121
[120]: https://github.com/openlawlibrary/taf/pull/120
[118]: https://github.com/openlawlibrary/taf/pull/118
[117]: https://github.com/openlawlibrary/taf/pull/117
[116]: https://github.com/openlawlibrary/taf/pull/116
[114]: https://github.com/openlawlibrary/taf/pull/114

## [0.3.1] - 03/21/2020

### Added

### Changed

- Move safely_get_json to base git repository class ([105])

### Fixed

- `update_role_keystores` fix ([112])
- `create_repo` fix ([111])
- Load repositories exits early if the authentication repo has not commits ([106])
- Fix `clone_or_pull` ([105])

[112]: https://github.com/openlawlibrary/taf/pull/112
[111]: https://github.com/openlawlibrary/taf/pull/111
[106]: https://github.com/openlawlibrary/taf/pull/106
[105]: https://github.com/openlawlibrary/taf/pull/105

## [0.3.0] - 03/03/2020

### Added

- Add a check if at least one rpeository was loaded ([102])
- Add `*args` and `**kwargs` arguments to repository classes ([102])
- Add a method for instantiating TUF repository at a given revision ([101])
- Add support for validating delegated target repositories to the updater ([101])
- Add delegations tests ([98])
- Add support for delegated targets roles ([97], [98], [99], [100])

### Changed

- Renamed `repo_name` to `name` and `repo_path` to `path` ([101])
- Updated `add_targets` so that it fully supports delegated roles ([98])
- Refactored tests so that it is possible to create and use more than one taf repository ([98])
- Separated commands into sub-commands ([96])
- Use `root-dir` and `namespace` instead of `target-dir` ([96])

### Fixed

- Fix init and create repo commands ([96])

[102]: https://github.com/openlawlibrary/taf/pull/102
[101]: https://github.com/openlawlibrary/taf/pull/101
[100]: https://github.com/openlawlibrary/taf/pull/100
[98]: https://github.com/openlawlibrary/taf/pull/98
[97]: https://github.com/openlawlibrary/taf/pull/97
[96]: https://github.com/openlawlibrary/taf/pull/96

## [0.2.2] - 01/06/2020

### Added

- Updater: support validation of multiple branches of target repositories ([91])
- Add a method which deletes all target files which are not specified in targets.json ([90])

### Changed

### Fixed

- Fix `update_target_repos_from_repositories_json` ([91])

[91]: https://github.com/openlawlibrary/taf/pull/91
[90]: https://github.com/openlawlibrary/taf/pull/90

## [0.2.1] - 12/19/2019

### Added

- Add `update_expiration_date` CLI command ([86])
- Add `set_remote_url` git method and branch as the input parameter of `list_commits` ([84])

### Changed

- Logging rework - use loguru library ([83])

### Fixed

- Fix `update_expiration_date_keystore` and `get_signable_metadata` ([86])
- Fix branch exists git function ([82])

[86]: https://github.com/openlawlibrary/taf/pull/86
[84]: https://github.com/openlawlibrary/taf/pull/84
[83]: https://github.com/openlawlibrary/taf/pull/83
[82]: https://github.com/openlawlibrary/taf/pull/82

## [0.2.0] - 11/30/2019

### Added

- Added commands for setting up yubikeys, exporting public keys and adding new signing keys ([79])
- Created standardized yubikey prompt ([79])

### Changed

### Fixed

- Creation of new repositories made more robust ([79])

[79]: https://github.com/openlawlibrary/taf/pull/79

## [0.1.8] - 11/12/2019

### Added

- Numerous new git methods ([74], [75])
- Initial [pre-commit](https://pre-commit.com/) configuration (black + flake8 + bandit) ([69])
- Add changelog ([69])
- Add pull request template ([69])

### Changed

- Updated validation of branches ([73])
- Move tests to the main package ([72])
- Updated _travis_ script ([69])
- Remove python 3.6 support ([69])
- Use _f-strings_ instead of _format_ ([69])

### Fixed

[75]: https://github.com/openlawlibrary/taf/pull/75
[74]: https://github.com/openlawlibrary/taf/pull/74
[73]: https://github.com/openlawlibrary/taf/pull/73
[72]: https://github.com/openlawlibrary/taf/pull/72
[69]: https://github.com/openlawlibrary/taf/pull/69

## [0.1.7] - 09/30/2019

### Added

- Add helper method to check if given commit has ever been validated ([65])

### Changed

- Pass scheme argument when loading _timestamp_ and _snapshot_ keys ([66])
- Updated default logs location ([67])

### Fixed

[65]: https://github.com/openlawlibrary/taf/pull/65
[66]: https://github.com/openlawlibrary/taf/pull/66
[67]: https://github.com/openlawlibrary/taf/pull/67

## [0.1.6] - 09/05/2019

### Added

### Changed

- Update oll-tuf version ([63])
- Remove utils function for importing RSA keys and refactor other files ([63])

### Fixed

- Fix azure pipeline script (include _libusb_ in wheels) ([63])

[63]: https://github.com/openlawlibrary/taf/pull/63

## [0.1.5] - 08/29/2019

- Initial Version

[keepachangelog]: https://keepachangelog.com/en/1.0.0/
[semver]: https://semver.org/spec/v2.0.0.html
[unreleased]: https://github.com/openlawlibrary/taf/compare/v0.35.0a1...HEAD
[0.35.0a1]: https://github.com/openlawlibrary/taf/compare/v0.34.1...v0.35.0a1
[0.34.1]: https://github.com/openlawlibrary/taf/compare/v0.34.0...v0.34.1
[0.34.0]: https://github.com/openlawlibrary/taf/compare/v0.33.2...v0.34.0
[0.33.2]: https://github.com/openlawlibrary/taf/compare/v0.33.1...v0.33.2
[0.33.1]: https://github.com/openlawlibrary/taf/compare/v0.33.0...v0.33.1
[0.33.0]: https://github.com/openlawlibrary/taf/compare/v0.32.4...v0.33.0
[0.32.4]: https://github.com/openlawlibrary/taf/compare/v0.32.3...v0.32.4
[0.32.3]: https://github.com/openlawlibrary/taf/compare/v0.32.2...v0.32.3
[0.32.2]: https://github.com/openlawlibrary/taf/compare/v0.32.1...v0.32.2
[0.32.1]: https://github.com/openlawlibrary/taf/compare/v0.32.0...v0.32.1
[0.32.0]: https://github.com/openlawlibrary/taf/compare/v0.31.2...v0.32.0
[0.31.2]: https://github.com/openlawlibrary/taf/compare/v0.31.1...v0.31.2
[0.31.1]: https://github.com/openlawlibrary/taf/compare/v0.31.0...v0.31.1
[0.31.0]: https://github.com/openlawlibrary/taf/compare/v0.30.2...0.31.0
[0.30.2]: https://github.com/openlawlibrary/taf/compare/v0.30.1...v0.30.2
[0.30.1]: https://github.com/openlawlibrary/taf/compare/v0.30.0...v0.30.1
[0.30.0]: https://github.com/openlawlibrary/taf/compare/v0.29.1...v0.30.0
[0.29.1]: https://github.com/openlawlibrary/taf/compare/v0.29.0...v0.29.1
[0.29.0]: https://github.com/openlawlibrary/taf/compare/v0.28.0...v0.29.0
[0.28.0]: https://github.com/openlawlibrary/taf/compare/v0.27.0...v0.28.0
[0.27.0]: https://github.com/openlawlibrary/taf/compare/v0.26.1...v0.27.0
[0.26.1]: https://github.com/openlawlibrary/taf/compare/v0.26.0...v0.26.1
[0.26.0]: https://github.com/openlawlibrary/taf/compare/v0.25.0...v0.26.0
[0.25.0]: https://github.com/openlawlibrary/taf/compare/v0.24.0...v0.25.0
[0.24.0]: https://github.com/openlawlibrary/taf/compare/v0.23.1...v0.24.0
[0.23.1]: https://github.com/openlawlibrary/taf/compare/v0.23.0...v0.23.1
[0.23.0]: https://github.com/openlawlibrary/taf/compare/v0.22.4...v0.23.0
[0.22.4]: https://github.com/openlawlibrary/taf/compare/v0.22.3...v0.22.4
[0.22.3]: https://github.com/openlawlibrary/taf/compare/v0.22.2...v0.22.3
[0.22.2]: https://github.com/openlawlibrary/taf/compare/v0.22.1...v0.22.2
[0.22.1]: https://github.com/openlawlibrary/taf/compare/v0.22.0...v0.22.1
[0.22.0]: https://github.com/openlawlibrary/taf/compare/v0.21.1...v0.22.0
[0.21.1]: https://github.com/openlawlibrary/taf/compare/v0.20.0...v0.21.1
[0.21.0]: https://github.com/openlawlibrary/taf/compare/v0.20.0...v0.21.0
[0.20.0]: https://github.com/openlawlibrary/taf/compare/v0.19.0...v0.20.0
[0.19.0]: https://github.com/openlawlibrary/taf/compare/v0.18.0...v0.19.0
[0.18.0]: https://github.com/openlawlibrary/taf/compare/v0.17.0...v0.18.0
[0.17.0]: https://github.com/openlawlibrary/taf/compare/v0.16.0...v0.17.0
[0.16.0]: https://github.com/openlawlibrary/taf/compare/v0.15.0...v0.16.0
[0.15.0]: https://github.com/openlawlibrary/taf/compare/v0.14.0...v0.15.0
[0.14.0]: https://github.com/openlawlibrary/taf/compare/v0.13.4...v0.14.0
[0.13.4]: https://github.com/openlawlibrary/taf/compare/v0.13.3...v0.13.4
[0.13.3]: https://github.com/openlawlibrary/taf/compare/v0.13.2...v0.13.3
[0.13.2]: https://github.com/openlawlibrary/taf/compare/v0.13.1...v0.13.2
[0.13.1]: https://github.com/openlawlibrary/taf/compare/v0.13.0...v0.13.1
[0.13.0]: https://github.com/openlawlibrary/taf/compare/v0.12.0...v0.13.0
[0.12.0]: https://github.com/openlawlibrary/taf/compare/v0.11.1...v0.12.0
[0.11.1]: https://github.com/openlawlibrary/taf/compare/v0.11.0...v0.11.1
[0.11.0]: https://github.com/openlawlibrary/taf/compare/v0.10.1...v0.11.0
[0.10.1]: https://github.com/openlawlibrary/taf/compare/v0.10.0...v0.10.1
[0.10.0]: https://github.com/openlawlibrary/taf/compare/v0.9.0...v0.10.0
[0.9.0]: https://github.com/openlawlibrary/taf/compare/v0.8.1...v0.9.0
[0.8.1]: https://github.com/openlawlibrary/taf/compare/v0.8.1...v0.8.1
[0.8.0]: https://github.com/openlawlibrary/taf/compare/v0.7.2...v.0.8.0
[0.7.2]: https://github.com/openlawlibrary/taf/compare/v0.7.1...v0.7.2
[0.7.1]: https://github.com/openlawlibrary/taf/compare/v0.7.0...v0.7.1
[0.7.0]: https://github.com/openlawlibrary/taf/compare/v0.6.1...v0.7.0
[0.6.1]: https://github.com/openlawlibrary/taf/compare/v0.6.0...v0.6.1
[0.6.0]: https://github.com/openlawlibrary/taf/compare/v0.5.2...v0.6.0
[0.5.2]: https://github.com/openlawlibrary/taf/compare/v0.5.1...v0.5.2
[0.5.1]: https://github.com/openlawlibrary/taf/compare/v0.5.0...v0.5.1
[0.5.0]: https://github.com/openlawlibrary/taf/compare/v0.4.1...v0.5.0
[0.4.1]: https://github.com/openlawlibrary/taf/compare/v0.4.0...v0.4.1
[0.4.0]: https://github.com/openlawlibrary/taf/compare/v0.3.1...v0.4.0
[0.3.1]: https://github.com/openlawlibrary/taf/compare/v0.3.0...v0.3.1
[0.3.0]: https://github.com/openlawlibrary/taf/compare/v0.2.2...v0.3.0
[0.2.2]: https://github.com/openlawlibrary/taf/compare/v0.2.1...v0.2.2
[0.2.1]: https://github.com/openlawlibrary/taf/compare/v0.2.0...v0.2.1
[0.2.0]: https://github.com/openlawlibrary/taf/compare/v0.1.8...v0.2.0
[0.1.8]: https://github.com/openlawlibrary/taf/compare/v0.1.7...v0.1.8
[0.1.7]: https://github.com/openlawlibrary/taf/compare/v0.1.6...v0.1.7
[0.1.6]: https://github.com/openlawlibrary/taf/compare/v0.1.5...v0.1.6
[0.1.5]: https://github.com/openlawlibrary/taf/compare/7795682e5358f365c140aebde31230602a5d8f0b...v0.1.5
