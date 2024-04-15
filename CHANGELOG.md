# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog][keepachangelog],
and this project adheres to [Semantic Versioning][semver].

## [Unreleased]

### Added

- Clone target repositories to temp ([412, 418])
- Add architecture overview documentation ([405])

[412]: https://github.com/openlawlibrary/taf/pull/412
[405]: https://github.com/openlawlibrary/taf/pull/405

### Changed

- Check if repositories are clean before running the updater ([416])
- Only show merging commits messages if actually merging commits. Rework logic for checking if a commits should be merged ([404], [415])

[418]: https://github.com/openlawlibrary/taf/pull/418
[416]: https://github.com/openlawlibrary/taf/pull/416
[415]: https://github.com/openlawlibrary/taf/pull/415
[404]: https://github.com/openlawlibrary/taf/pull/404

### Fixed

## [0.29.3] - 03/15/2024

### Added

### Changed

### Fixed

- Disable check if metadata files at revision match ([403])

[403]: https://github.com/openlawlibrary/taf/pull/403

## [0.29.2] - 03/14/2024

### Added

- Add a command for adding delegated paths to a role ([391])
- Check if metadata files at revision match those downloaded by TUF updater ([389])

### Changed

### Fixed

- Fix `clone_or_pull` ([402])

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

[387]: https://github.com/openlawlibrary/taf/pull/381
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

- Split tests into separate packages [(353)]
- Minor add/remove target repository improvements [(351)]
- Bump `cattrs` ([349])
- Improve CLI error handling ([346])
- Update signing keys loading. Add a flag for specifying if the user will be asked to manually enter a key ([346])
- Remove default branch specification from updater ([343])
- Updater: only load repositories defined in the newest version of repositories.json ([341])
- Updater: automatically determine url if local repository exists ([340])
- Remove hosts and hosts.json ([330])

### Fixed

- Fix list targets in case when the target repo is not up to date with remote ([357])
- Fix repositories.json update when adding new target repository [(351)]
- Fix error when keystore path is not provided [(351)]
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
[unreleased]: https://github.com/openlawlibrary/taf/compare/v0.29.3...HEAD
[0.29.3]: https://github.com/openlawlibrary/taf/compare/v0.29.2...v0.29.3
[0.29.2]: https://github.com/openlawlibrary/taf/compare/v0.29.1...v0.29.2
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
