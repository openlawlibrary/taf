# TAF

TAF (The Archive Framework) is an implementation of archival authentication. In other words, TAF ensures that a git repository can be securely cloned/updated and authenticated. In our case, a git repository is a collection of thousands of XML documents and represents a Library of official legal material, but TAF can be used to secure any git repository, regardless of its content.

A git repository can be compromised in a number of ways:

- an attacker could hack a user's account on a code hosting platform, like GitHub or GitLab,
- an attacker could hack the hosting platform,
- an attacker could gain access to a developer's personal computer.

This attacker could then:

- upload a new GPG key to GitHub,
- push new commits to any repository,
- add another authorized user with write access,
- unprotected the master branch of any of the repositories and force push to it.

TAF's goal is not to prevent any of the attacks listed above from happening, but to detect that an attack took place and cancel an update if that is the case. So, TAF should be used instead of directly calling `git pull` and `git clone`.

TAF's implementation strongly relies on [The Update Framework (TUF)](https://theupdateframework.github.io), which helps developers maintain the security of a software update system and provides a flexible framework and specification that developers can adopt into any software update system.

Further reading:

1. [UELMA whitepaper](whitepapers/UELMA-Open-Law-White-Paper.pdf)
1. [TAF implementation and integration with TUF](docs/updater/specification.md)

## Installation Steps

From _PyPI_

```bash
pip install taf
```

From source:

```bash
pip install -e .
```

Install extra dependencies when using _Yubikey_:

```bash
pip install taf[yubikey]
```

Add bash completion:

1. copy `taf-complete.sh` to user's directory
1. add `source ./taf-complete.sh` to `~/.bash_profile` or `~/.bashrc`
1. source `~/.bash_profile`

## Development Setup

We are using [pre-commit](https://pre-commit.com/) to run _black_ code formatter, _flake8_ and _bandit_ code quality checks.

```bash
pip install -e .[dev]
pip install -e .[test]

pre-commit install # registers git pre-commit hook

pre-commit run --all-files # runs code formatting and quality checks for all files
```

NOTE: For _Windows_ users: Open [settings.json](.vscode/settings.json) and replace paths.

## Running Tests

To run tests with mocked Yubikey:

```bash
pytest
```

To run tests with real Yubikey:

1. Insert **test** Yubikey
2. Run `taf setup_test_key`
   WARNING: This command will import targets private key to signature slot of your Yubikey, as well as new self-signed x509 certificate!
3. Run `REAL_YK=True pytest` or `set REAL_YK=True pytest` depending on platform.

## Platform-specific Wheels

1. Open https://dev.azure.com/openlawlibrary/TAF/_build
2. Click on latest build
3. Open _Summary_ tab
4. Under _Build artifacts published_, click on \*wheels to download zip

More info in [devops document](./docs/devops.md).

## Building Wheels on Ubuntu 16.04 and 18.04

**Binary wheels exists only for macOS, windows-32bit and windows-64bit platforms for python 3.10!**

- Install dependencies

```bash
sudo add-apt-repository ppa:jonathonf/python-3.10
sudo apt-get update
sudo apt-get install python3.10
sudo apt-get install python3.10-venv
sudo apt-get install python3.10-dev
sudo apt-get install swig
sudo apt-get install libpcsclite-dev
sudo apt-get install libssl-dev
sudo apt-get install libykpers-1-dev
```

- Create virtual environment

```bash
python3.6 -m venv env
pip install --upgrade pip
pip install wheel
pip install taf
```

- Test CLI

```bash
taf
```
