# TAF (The Archive Framework)

TAF is a framework that aims to provide archival authentication
and ensure that Git repositories can be securely cloned/updated. TAF's implementation
strongly relies on [The Update Framework (TUF)](https://theupdateframework.github.io),
which helps developers maintain the security of a software update system. It provides a
flexible framework and specification that developers can integrate into any software update
system. TAF integrates Git with TUF:

- TUF targets were modified to authenticate Git commits instead of individual files.
  This reduces the metadata size and simplifies authentication.
- The TUF metadata repository storage utilizes Git. That means TUF metadata files are
  stored in a Git repository, which is referred to as an authentication repository.

When a TAF authentication repository is cloned, all target repositories are also cloned, and
TUF validation is performed against every commit since the repository's inception. When a TAF
repository is updated, data is fetched from upstream and each commit is authenticated. A TAF
clone/update differs from a standard Git clone/fetch in that remote commits aren't added to the
local Git repositories until they've been fully authenticated locally. TAF can be used to secure
any git repository, regardless of its content.

## Threats

A git repository can be compromised in several ways:

- An attacker might hack a user's account on a code hosting platform, like GitHub or GitLab.
- An attacker might compromise the hosting platform itself.
- An attacker might gain access to a developer's personal computer.

Such an attacker could then:

- Upload a new GPG key to GitHub.
- Push new commits to any repository.
- Add another authorized user with write access.
- Unprotect the master branch of any repository and force-push to it.

TAF's primary objective is not to prevent the attacks listed above but rather to detect when
an attack has occurred and halt an update if necessary. Thus, TAF should be used instead of
directly calling `git pull` and `git clone`.


## Further reading

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

We are using [pre-commit](https://pre-commit.com/) to run _black_ code formatter, _flake8_ and _bandit_ code quality checks,
as well as _Mypy_ static type checker.

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


## Installing Wheels on Windows and MacOS

The newer versions of TAF do not require additional setup, and there are no platform-specific wheels needed. However, older versions required certain platform-specific DLLs, which the CI would copy to `taf/libs` before building a wheel. Therefore, it's important to install the appropriate platform-specific wheel if you're using an older version.


## Installing Wheels on Ubuntu


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
python3.10 -m venv env
pip install --upgrade pip
pip install wheel
pip install taf
```

- Test CLI

```bash
taf
```

## Related Projects

There are projects which share similar ideas to TAF.

### gittuf

[gittuf](https://github.com/gittuf/gittuf) is a security layer for Git repositories. gittuf enables
a security policy to be specified for a Git repository, such that any user who has read access to
the repository may verify compliance with it. While similar in goals, gittuf differs from TAF in its
architecture and intended use case.

TAF relies on a multi-repository architecture: TUF metadata resides in an authentication repository,
which is used to validate the changes made to any number of target repositories. For detailed
information on TAF's architecture, see [the TAF architecture document](docs/architecture.md). TAF is
intended to verify changes to an archive consisting of any number of Git repositories.

gittuf relies on a Reference State Log (RSL) that encodes a log of repository activity, as well as
security policy, loosely based on TUF metadata. This log is then used to enable the validation of
every commit in the protected repository. For detailed information on gittuf's architecture, see
[the gittuf design document](https://github.com/gittuf/gittuf/blob/main/docs/design-document.md).
gittuf may be used to verify changes to any single Git repository (multi-repository support is
in progress).

## Acknowledgements

This project was made possible in part by the Institute of Museum and Library Services [(LG-246285-OLS-20)](https://www.imls.gov/grants/awarded/lg-246285-ols-20)
