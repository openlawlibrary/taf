# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog][keepachangelog],
and this project adheres to [Semantic Versioning][semver].

## [Unreleased]

### Added

- Add --version option to cli ([239])
- Add TAF's repository classes and repositoriesdb's documentation ([237])
- Add `--ff-only` to git merge ([235])
- Added format-output flag to update repo cli ([234])
- Cache loaded git files ([228])
- Add a flag for generating performance reports of update calls and print total update execution time ([228])

### Changed

- Update `targets_at_revisions` - only update a list of roles if a metadata file was added ([228])

### Fixed


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

[Unreleased]: https://github.com/openlawlibrary/taf/compare/v0.16.0...HEAD
[0.14.0]: https://github.com/openlawlibrary/taf/compare/v0.15.0...v0.16.0
[0.14.0]: https://github.com/openlawlibrary/taf/compare/v0.14.0...v0.15.0
[0.14.0]: https://github.com/openlawlibrary/taf/compare/v0.13.4...v0.14.0
[0.13.4]: https://github.com/openlawlibrary/taf/compare/v0.13.3...v0.13.4
[0.13.3]: https://github.com/openlawlibrary/taf/compare/v0.13.2...v0.13.3
[0.13.2]: https://github.com/openlawlibrary/taf/compare/v0.13.1...v0.13.2
[0.13.1]: https://github.com/openlawlibrary/taf/compare/v0.13.0...v0.13.1
[0.13.0]: https://github.com/openlawlibrary/taf/compare/v0.12.0...v0.13.0
[0.12.0]: https://github.com/openlawlibrary/taf/compare/v0.11.2...v0.12.0
[0.11.1]: https://github.com/openlawlibrary/taf/compare/v0.11.1...v0.11.2
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
