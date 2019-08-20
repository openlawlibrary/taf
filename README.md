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

TAF's implementation strongly relies on [The Update Framework (TUF](https://theupdateframework.github.io)), which helps developers maintain the security of a software update system and provides a flexible framework and specification that developers can adopt into any  software update system.

Further reading:

1. [UELMA whitepaper](whitepapers/UELMA-Open-Law-White-Paper.pdf)
1. [TAF implementation and integration with TUF](docs/TUF/tuf-specification.md)

## RUNNING TESTS

To run tests with mocked Yubikey:

```bash
pytest
```

To run tests with real Yubikey:

1. Insert **test** Yubikey
2. Run `taf setup_test_yubikey`
   WARNING: This command will import targets private key to signature slot of your Yubikey, as well as new self-signed x509 certificate!
3. Run `REAL_YK=True pytest` or `set REAL_YK=True pytest` depending on platform.
