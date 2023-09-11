# Quick Start

This documents describes the most useful commands. See [this overview](repo-creation-and-update-util.md) for more information.

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
          "law": {
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
  key and it will not be necessary to insert the YubiKye (unless the threshold of sining keys is not reached, like when
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

`taf yubikey setup-signing-key`

WARNING: This command will delete the YubiKey's existing data. New repositories can be created using already set
up YubiKeys.

## Create a repository

Use the `repo create` command to create a new authentication repository:

```bash
taf repo create --path auth-path --keystore keystore_path --keys-description keys-description.json --commit --test
```

- `path` is an optional parameter which represents a path to a folder where the new authentication repository's content should be stored to e.g. `test/law`. If not specified, the repository will be created inside the current working directory.
- `keys-description` was described at the top of this document
- `keystore` is the location of the keystore files. Use this options if the keystore files were previously generated and not all metadata files should be signed using Yubikeys. This location can also be defined using the `keystore` property of the `keys-description` json.
- `commit` flag determines if the changes should be automatically committed
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

IMPORTANT: If the command was run without the commit flag, commit the changes before updating metadata files
or adding targets. The updater will raise and error if version numbers of metadata files in two subsequent
commits differ by more than one!

## Update targets

To update authentication repository's target files based on the current state of the target repositories use
`taf targets update-and-sign-targets`.  This command writes the current top commit and branch name of all
repositories listed in `repositories.json` to appropriate target files and automatically signs all updated
targets metadata files, as well as snapshot and timestamp.

```bash
taf targets update-and-sign-targets --path auth-path --keystore E:\\keystore
```

- `path` is an optional parameter which represents a path to a folder where the new authentication repository's content should be stored to e.g. `test/law`. If not specified, the repository will be created inside the current working directory.
`keystore` defines location of the keystore files. If a key is not in the provided keystore, or if keystore
location is not specified when calling the command, it will be necessary to either use previously set up
Yubikey for signing, or directly paste key values.
