# Setting up a new library

This document describes how to create a new authentication repository with all of the necessary content. The first step if to create an initialization file.

## `keys-description`

`keys-description` is a dictionary which contains information about the roles and their keys. The easiest way to specify it is to define it in a `.json` file and provide path to that file when calling various commands. For example:

```
{
  "yubikeys": {
    "user1": {
      "public": "-----BEGIN PUBLIC KEY-----\nMIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEAtdvJF1Q7fRNTQfgGMH/W\n2Sb4O/PemLHKcBj6Q1Nadvii+lF+lfsD/VqzEuNaM2fpJpostWzJR1jdeyjRZS9G\ndToEA9iSD0MczHRLWa9a1NMcPBC/Edts1oXogk23+NSL/Ugc5H+WikDuwMMYhA3o\nNgVgAtfDfJQJFkbI033DwcYjbBmlt/gnTVNUSHuoG8M2EurchMnZZIqSawEaL82Q\nIFUhEuGSljcb/WRj6XHY7upCvjJOMN2kH/zz4kGR8j5t61TKiLiepjunuQMGg+fl\njEm4v0fandpwWLdx7kYSbftmbQjnuPhBd3g3BQ721O4dYkLA/ncca9XryLqN8Cac\ngQIDAQAB\n-----END PUBLIC KEY-----",
      "scheme": "rsa-pkcs1v15-sha256"
    },
    "user2": {
      "public": "-----BEGIN PUBLIC KEY-----\nMIIBojANBgkqhkiG9w0BAQEFAAOCAY8AMIIBigKCAYEA95lvROpv0cjcXM4xBYe1\nhNYajb/lfM+57UhTteJsTsUgFefLKJmvXLZ7gFVroHTRzMeU0UvCaEWAxFWJiPOr\nxYBOtClSiPs4e0a/safLKDX0zBwT776CqA/EJ/P6+rPc2E2fawmq1k8RzalJj+0W\nz/xr9fKyMpZU7RQjJmuLcyqfUYTdnZHADn0CDM54gBZ4dYDGGQ70Pjmc1otq4jzh\nI390O4W9Gj9yXd6SyxW2Wpj2CI3g4J0pLl2c2Wjf7Jd4PVNxLGAFOU2YLoI4F3Ri\nsACFUWjfT7p6AagSPStzIMik1YfLq+qFUlhn3KbNMAY9afkvdbTPWT+vajjsoc4c\nOAex1y/uZ2npn/5Q0lT7gMH/JxB3GmAYHCew5W6GmO2mRfNO3J8A+hqS3nKGEbfR\ncb7V176O/tdRM0HguIWAuV75khrCpGLx/fZNAMFf3Q9p0iJsx9p6gCAHERi5e4BJ\nSCBkbtVGGsQ7JM7ptSiLLgi79hIXWehZFUIjuU7a2y4xAgMBAAE=\n-----END PUBLIC KEY-----",
      "scheme": "rsa-pkcs1v15-sha256"
    },
    "userYK": {
      "scheme": "rsa-pkcs1v15-sha256"
    }
  },
  "roles": {
      "root": {
        "threshold": 1,
        "yubikeys": [
          "user1", "user2"
        ]
      },
      "targets": {
        "threshold": 1,
        "yubikeys": [
          "user1", "user2"
        ],
        "delegations": {
          "delegated_role": {
            "paths": [
              "dir1/*",
              "path1",
              "path2"
              ],
            "threshold": 1,
            "yubikeys": [
              "user1", "user2"
            ],
            "delegations": {
              "inner_role": {
                "paths": ["path3"],
                "yubikeys": ["user1", "user2"]
              }
            }
          }
        }
      },
      "snapshot": {
        "number": 1,
        "threshold": 1,
        "scheme": "rsa-pkcs1v15-sha256"
      },
      "timestamp": {

      }
    },
  "keystore": "D:\\oll\\library\\oll-test-repos\\keystore-dev\\keystore-dev"
}
```

NOTE: in this example, schemes were specified in order to provide an example of how to do so.
At the moment, all keys should have the same signing scheme.
The default scheme is `rsa-pkcs1v15-sha256`. Delegated target roles are optional - if all target files
should be signed using the `targets` key, there is no point in defining delegated target roles.

-`yubikeys` contains information about YubiKeys which can be references when specifying role's keys. Each key is
mapped to a custom name (like `user1`, `user2`, `userYK`) and these names will be used to reference these keys
while setting up a role, instead of the generic names derived from names of the roles. Additional information
includes:
  - `public`- public key exported from the YubiKey. The specified key will be registered as the role's verification
  key and it will not be necessary to insert the YubiKey (unless the threshold of signing keys is not reached, like when
  public keys of all used YubiKeys are specified)
  - `scheme` - signing scheme (can be ommitted, default scheme is `rsa-pkcs1v15-sha256`)
- `roles` contains information about roles and their keys, including delegations:
  -  `number` - total number of the role's keys
  - `length` - length of the role's keys. Only needed when this json is used to generate keys.
  - `threshold` - role's keys threshold - with how many different keys must a metadata files be signed
  - `yubikey` - a flag which signalizes that the keys should be on YubiKeys (deprecated)
  - `yubikeys` - a list of names of YubiKeys listed in the `yubikeys` section
  - `scheme` - signing scheme
  - `delegations` and `paths` - delegated roles of a targets role. For each delegated role, it is necessary to specify `paths`. That is, files or directories that the delegated role can sign. Paths are specified using glob expressions. In addition to paths, it is possible to specify the same properties of delegated roles as of main roles (number or keys, threshold, delegations etc.).
  In this example, `delegated_role` is a delegated role of the `targets` role and `inner_role` is a delegated role of `delegated_role`
  - `terminating` - specifies if a delegated role is terminating (as defined in TUF - if a role is trusted with a certain file which is not found in that role an exceptions is raised if terminating is `True`. Affects the updater).
- `keystore` - location of the keystore files. This path can also be specified through an input parameter. This is the location where the keys will be saved to when being generated and where they will be read from when signing metadata files.

Names of keys must follow a certain naming convention. That is,their names are composed of the role's name
and a counter (if there is more than one key). E.g. `root1`', `root2`, `targets1`, `targets2`, `snapshot` etc.

If a property is omitted from the specification, it will have the default value. The default values are:
- `number=1`
- `length=3072` Note: If the generated key should be moved to a YubiKey 4, this value must not exceed 2048
- `threshold=1`
- `scheme=rsa-pkcs1v15-sha256`

The `keys-description` option can either directly contain the described json, or be a path to a file
which contains it.
In cases when this dictionary is not provided, it is necessary to enter the needed
information when asked to do so, or confirm that default values should be used.

## Generate keys

In order to create a new repository, it is necessary to decide which keys are to be used - YubiKeys, keystore files
or a combination of them. It is not recommended to use keystore files for signing root and targets metadata (including all delegated roles) of production repositories. Start by creating `keys-description.json`.

Keys can be generated while creating a new repository if they don't already exist, but can also be generated in advance.
To generate new keystore files, call:

`taf keystore generate destination_path keys-description.json`

This command will only generate a key of roles explicitly listed in the input - so add empty snapshot and timestamp
dictionaries if these keys should be generated as well.

To set up new YubiKyes, call

`taf yubikey setup_signing_key`

**_WARNING:_**: This command will delete the YubiKey's existing data. New repositories can be created using already
set up YubiKeys.

## Create a repository

Use the `repo create` command to create a new authentication repository:

```bash
taf repo create --path auth_path --keystore keystore_path --keys-description keys-description.json --test
```

- `path` is an optional parameter which represents a path to a folder where the new authentication repository's content should be stored to e.g. `test/law`. If not specified, the repository will be created inside the current working directory.
- `keys-description` is the previously described dictionary containing information about roles, keys and optionally keystore location. If one or more keys should be loaded from the disk their location can be determined based on `keystore` property of this json.
- `keystore` is the location of the keystore files. Use this options if the keystore files were previously generated and not all metadata files should be signed using Yubikeys. This location can also be defined using the `keystore` property of the `keys-description` json.
- `test`  flag determines if a special target file called `test-auth-repo` will be created. That
signalizes that an authentication repository is a test repository. When calling the updater,
it's necessary to use a flag which makes it clear that it is a test repository which is to
be updated.

It is not necessary to generate keys or initialize Yubikeys prior to calling this command.
For each role, keys can be:

- loaded from the keystore files if they already exist
- generated and stored to keystore files
- loaded from previously initialized Yubikeys
- generated and stored on a Yubikey (this deletes all existing data from that key)

Changes will be committed automatically, unless the `--no-commit` flag is provided.
If changes are not committed automatically, it's important to commit manually before updating metadata files
or adding targets. The updater will raise an error if version numbers of metadata files in two subsequent
commits differ by more than one!

## Set up remote repositories

Create new repositories in your GitHub organization - an authentication repository and one for each target repository.
DO NOT ADD THE INITIAL FILES when creating authentication repository's remote repository. The first commit should contain initial metadata files. If something is added
to the target repositories, thus creating the initial commit, do not commit anything else before signing the initial commit (unless that target repository can contain unauthenticated commits and the initial commit does not need to be authenticated, which is determined by the `allow-unauthenticated-commits` property specified per target repo in `repositories.json`). Set remote of the locally created authentication repository, commit initial metadata and target files and push them. E.g:

```
cd test\auth_repo
git remote add origin https://github.com/test-org/auth_repo
git add -A
git commit -m "Initial commit"
git push --set-upstream origin main
```

Clone the target repositories to continue with the setup.

## Create special target files

In order to be able to use the updater to pull and validate an authentication repository and its targets, or a whole
hierarchy of repositories, it is necessary to create certain target files. See [updater's specification](./updater/specification.md) for more details about these files.

### `repositories.json`

This target files defines target repositories of an authentication repository (repositories which will be pulled
while updating the authentication repository). Each target files should be referenced by its namespace prefixed
name:

```
{
    "repositories": {
        "test/repo1: {
            "custom": {
    "custom_property": "custom_value"
            }
        },
        "test/repo2": {
            "custom": {
    "custom_property": "custom_value",
    "allow-unauthenticated-commits":true
            }
        }
    }
}
```

It is recommended not to specify URLs in `repsositories.json`, as that has been deprecated.

Notice custom property `allow-unauthenticated-commits`. If it is set to `true` the target repositories can contain unauthenticated commits in-between authenticated ones. This means that it is not necesary to sign the corresponding target files after every commit.

### `mirrors.json`

This file is used to define URLs of the repositories:

```
{
    "mirrors": [
        "http://github.com/{org_name}/{repo_name}"
    ]
}
```

`org_name` and `repo_name` are placeholders and they will be replaced by namespace and repository's name as defined
in `repositories.json`. E.g. `test` and `repo1` for the first repo, `test` and `repo2` in the second repository's case.

### `dependencies.json`

This target files is optional, but needs to be defined if the authentication repository references other authentication repositories (to define hierarchies), to make a use of the out-of-band authentication check.

This is an example where there are no hierarchies, but we want to define the current repository's expected commit and want to make use of the update handlers.

```
{
    "dependencies": {
        "test/auth_repo": {
            "out-of-band-authentication": "763bcd15812635f57678fea0fef794b7c271f055"
        }
    }
}
```

This is an example where we defined a hierarchy (define two authentication repository which are seen as the current repository's children):

```
{
    "dependencies": {
        "test1/auth_repo": {
            "out-of-band-authentication": "222bcd15812635f57678fea0fef794b7c271fabc"
        },
        "test2/auth_repo": {
            "out-of-band-authentication": "333bcd15812635f89001fea0fef794b7c271f456"
        }
    }
}
```

### `protected/info.json`

Optional file with authentication repository's metadata. Currently, we support specifying either `library_dir` and
having `info.json` metadata, or specifying `clients-auth-path` in `taf repo update` command. When running taf update
by specifying `library-dir`, `namespace/repo_name` is automatically extracted from `info.json` and appended to
`library_dir`.

Example:

```
{
  "namespace": "some_org_name",
  "name":  "some_repo_name"
}
```

## Sign added targets

After updating target files, it is necessary to sign them. That means updating and signing
the metadata files. This can be accomplished by calling the `targets sign` command. It updates all targets
metadata files corresponding to roles responsible for modified target files, `snapshot`
and `timestamp.json`

```bash
taf targets sign --path auth_path --keys-description keys_description.json
```

or

```bash
taf targets sign --keys-description keys_description.json
```

- `path` is an optional parameter which represents authentication repository's path. If not specified, the repository will be expected to be inside the current working directory.
- `keys-description` is the previously described dictionary containing information about roles, keys and optionally keystore location. If one or more keys should be loaded from the disk their location can be determined based on `keystore` property of this json.
- `keystore` defines location of the keystore files and should be used when keystore location is not specified in `keys-description` or when not using `keys-description` option, but one or more keys should be loaded from the disk.

Unless the `--no-commit` flag is specified, changes will be committed automatically. If you want to be on the safe side, run local validation to be sure that the authentication repository is in a valid state:

```bash
taf repo validate auth_path
```

Finally, push the changes.

## Add targets corresponding to target repositories

Information about target repositories of an authentication repository is listed in  `repositories.json`.
However, data used to validate these repositories (most importantly commit and branch) is stored in target files.
That is, files inside authentication repository's `targets` folder named after the target repositories.
Names of target repositories are keys in `repositories.json`. Files inside this `targets` folder are protected by
TUF. TAF might ignore a repository if there is no corresponding target file in `targets`.

Initial creation of these target files can be done manually, or through an automated process implemented
outside of TAF. To create them using TAF and sign initial commits of target repositories, use
`targets update_and_sign_targets`. Unless `allow-unauthenticated-commits` is set to `true` in `repositories.json`
for a target repository, it is necessary to update the corresponding target files of the authentication repository
after every commit.

**_WARNING:_**: If you added initial README or license using the GitHub interface, register those commits before making further changes.

```bash
taf targets update-and-sign --path E:\\root\\namespace\\auth_repo --keystore E:\\keystore
```

or

```bash
taf targets update-and-sign --keystore E:\\keystore
```

will sign all target repositories listed in `repositories.json`


## Run the updater

Run the updater to make sure that everything has been set up correctly. If errors occur, you
might have not pushed everything. Read the update log and make sure that every repository
was recognized as a target repository (that the names and ulrs are correct throughout the
special target files). The updater will create a directory called `_auth_repo_name` in the
library root directory and write the last validated commit in a file directly inside it.

**To trigger validation from the first commit should that sound useful, delete this directory**

The updater will check out the last validated commits, so to continue working, checkout the default branch again.

For more information about the updater and how to use it, see [the update process document](./updater/update_process.md)

## Update metadata files if they expired

By default, timestamp needs to be resigned every day, while snapshot expires a week after being signed. The updater will raise an error if the top metadata file has expired. To resign metadata files, run:

```bash
taf metadata update-expiration-dates --path auth_repo_path --keystore keystore_path --role targets1 --role targets2 --interval days
```

or

```bash
taf metadata update-expiration-dates --keystore keystore_path --role targets1 --role targets2 --interval days
```

- `path` is an optional parameter which represents authentication repository's path. If not specified, the repository will be expected to be inside the current working directory.
- `role` represents a role whose metadata's expiration date should be updated - `root`, `targets`, `snapshot`, `timestamp`, delegated targets role.
- `keystore path` is the location of the keystore files. Can be omitted if YubiKeys should be used instead.
- `interval` refers to the number of days added to today's date to calculate the expiration date.

When a metadata file is updated, all other metadata files which need to be updated according to TUF specification
are updated as well. So, when `snapshot` is updated, `timestamp` is updated too. When `root`, `targets` or a
delegated target role is updated, both `snapshot` and `timestamp` are updated as. This is done automatically
to ensure that the repository will stay valid.

A few examples:

```bash
taf metadata update-expiration-date auth_repo_path targets --keystore keystore_path --interval days
```

```bash
taf metadata update-expiration-date auth_repo_path snapshot --keystore keystore_path --interval days
```

```bash
taf metadata update-expiration-date auth_repo_path timestamp --keystore keystore_path --interval days
```

Unless explicitly specified, changes are committed automatically.

**_WARNING:_**: If the command is run twice without committing, and both changes are committed
afterwards, the repository will end up in an invalid state. `snapshot` and `timestamp` version
will be increased by 2 between subsequent commits, which is not valid.


