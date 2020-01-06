# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog][keepachangelog],
and this project adheres to [Semantic Versioning][semver].

## [Unreleased]

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

[Unreleased]: https://github.com/openlawlibrary/pygls/compare/v0.2.1...HEAD
[0.2.1]: https://github.com/openlawlibrary/taf/compare/v0.2.0...v0.2.1
[0.2.0]: https://github.com/openlawlibrary/taf/compare/v0.1.8...v0.2.0
[0.1.8]: https://github.com/openlawlibrary/taf/compare/v0.1.7...v0.1.8
[0.1.7]: https://github.com/openlawlibrary/taf/compare/v0.1.6...v0.1.7
[0.1.6]: https://github.com/openlawlibrary/taf/compare/v0.1.5...v0.1.6
[0.1.5]: https://github.com/openlawlibrary/taf/compare/7795682e5358f365c140aebde31230602a5d8f0b...v0.1.5
