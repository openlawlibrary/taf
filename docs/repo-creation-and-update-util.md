# Authentication repository creation and update utility

TAF provides a number of commands for creating and updating the authentication repositories.
Some of them focus on creation and initial setup of the repositories, while the others
provide an easy way to update information about authentication repository's target repositories
and roles.

## Arguments

Most commands have just one required argument, and that is authentication repository's path.
All other input parameters have default values or can be calculated based on this path, like
root directory and namespace. Both absolute and relative paths can be used. To make the examples
clearer, paths in this documentation are absolute.

## Options

The commands have similar options, most complex of which will be described in more detail
in the following sections.

### `library-dir` and `namespace`

Root directory. All target repositories are expected to be inside this repository, either directly
or inside a directory which is directly inside the root directory. That is, if names of targets
are not namespace prefixed, they are expected to be directly inside the root directory. Otherwise,
it is assumed that they are in a directory whose name corresponds to their namespace. For example,
if root directory is `E:\example` and namespace of the target repositories is `namespace1`,
these repositories are expected to be in `E:\example\namespace1` directory.
Unless these two parameters are explicitly set, they are determined based on authentication
repository's path, which is a required argument of all commands that have `library-dir` and `namespace`
options. It is assumed that the authentication repository is also inside a namespace directory.
By default, namespace is set to the authentication repository's namespace and `library-dir` to
the namespace directory's parent directory. If authentication repository's path is
`E:\example\namespace2\auth-repo`, `namespace` is set to `namespace2` and `library-dir` to
`E:\example`. If any of these assumptions is not correct (authentication and target repositories
do not have the same namespace, authentication repository is at a completely different location),
it is necessary to set root directory and namespace manually through `library-dir` and `namespace`
options.

Full names of target repositories combine their namespace and name. These names
are used as keys in `repositories.json` and to create a target files inside `targets` directory
corresponding to the targets repository. If a repository's namespaced name is
`namespace/TargetRepository`, a the target file will be called `TargetRepository` and
placed inside `namespace` directory inside `targets`. Namespace can be left empty. In that case the
target file will be directly inside `targets`.


### `keys-description`

To make commands such as creation of repositories, generation of keys and all others which
require certain information about roles and keys easier to use, an option called
`keys-description` was introduced. It allows passing in a json, like the following one:

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

### `scheme`

Many commands have the `scheme` optional parameter. It represents the signature scheme.
`rsa-pkcs1v15-sha256` is used by default.

## Commands

Commands are separated into several subcommands:

- `dependencies`, containing command for adding, updating and removing authentication repository's dependencies (other
authentication repositories which are linked with them)
- `keystore`, containing commands for generating keystore files.
- `metadata`, containing commands for updating metadata - adding signing keys and checking and updating expiration
dates of metadata files.
- `repo`, containing commands for creating, validating and updating new authentication repositories.
- `roles` , containing commands for adding and removing roles
- `targets`, containing commands for listing, adding and removing target repositories and signing targets (updating
target files corresponding to target repositories and signing all metadata files that need to be updated in order
to make sure that the authentication repository stays valid)
- `yubikey`, containing commands for setting up a new Yubikey and exporting public keys from Yubikeys

Here are some of the most important commands. Use the `--help` flag to see more information
about the commands. E.g. `taf repo create --help`.

### `keystore generate`

Generates and write rsa keypairs. Number of keys to generate per a metadata role, as well as their
lengths and passwords of the keystore files are specified using the `keys-description` parameter.

```bash
taf keystore generate E:\\OLL\\keystore_path  E:\\OLL\\data\\keys_description.json
```

The generated keys files will be saved to `E:\OLL\keystore_path`

### `repo create`

This command can be used to generate the initial authentication repository. The initial version
of all metadata files are created, but no targets are added.

```bash
taf repo create --path E:\\OLL\\auth_repo_path --keystore E:\\OLL\\keystore --keys-description E:\\OLL\\data\\keys.json --test
```

will generate a new authentication repository at `E:\OLL\auth_repo_path`, if `path` is provide, or inside
the current working directory, in case this parameter is omitted. There are several options
for signing metadata files - from keystore, by directly entering the key when prompted and by using
Yubikeys. If one or more keys are stored in the keystore, keystore path should be specified
when calling this command. If `keystore` is specified in `keys-description`, it is not necessary
to also use the `--keystore` option. All keys that do not already exist will be generated during
execution of this command. Keys can generated on the Yubikeys, but that will delete everything
stored on that key and will require new pins to be set. It is possible to reuse existing keys
stored on Yubikeys.

The generated files and folders will automatically be committed unless `--no-commit` unless flag is present. If the
new repository is only be meant to be used for testing, use `--test` flag. This will create a special
target file called `test-auth-repo`.

### `repo update`

Update and validate local authentication repository, its child authentication repositories (specified in `dependencies.json` )
and target repositories. When running the updater for the first time, it is necessary to specify the repository's remote url.
When updating an existing authentication repository, the url is automatically determined. Similarly, the repository's filesystem
path can, but does have to be specified. If it is omitted, it will be assumed that the repository is located inside the current
working directory. If the authentication repository and the target repositories are in the same root directory,
locations of the target repositories are calculated based on the authentication repository's
path. If that is not the case, it is necessary to redefine this default value using the `--clients-library-dir` option.
Names of target repositories (as defined in repositories.json) are appended to the root
path thus defining the location of each target repository. If names of target repositories
are namespace/repo1, namespace/repo2 etc and the root directory is E:\\root, path of the target
repositories will be calculated as `E:\\root\\namespace\\repo1`, `E:\\root\\namespace\\root2` etc.

When updating a test repository (that has the "test" target file), use `--authenticate-test-repo`
flag. An error will be raised if this flag is omitted in the mentioned case. Do not use this
flag when validating non-test repository as that will also result in an error.

For example:

```bash
taf repo update --path E:\\root\\namespace\\auth_repo --url https://github.com/orgname/auth-repo   --authenticate-test-repo
```

In this example, all target repositories will be expected to be in `E:\root`.


```bash
taf repo update E:\\root\\namespace\\auth_repo --url https://github.com/orgname/auth-repo --clients-library-dir E:\\target-repos
```

In this example, the target repositories will be expected to be in `E:\\target-repos`.

or just

```bash
taf repo update
```

if repository already exists and is located inside the current working directory.


If remote repository's url is a file system path, it is necessary to call this command with
`--from-fs` flag so that url validation is skipped. This option is mostly of interest to the
implementation of updater tests. To validate local repositories, use the `validate` command.

### `repo validate`

This command validates an authentication repository which is already on the file system
and its target repositories (which are also expected to be on the file system).
Does not clone repositories, fetch changes or merge commits. The main purpose of this command is
to make sure that the recent updates of the authentication repository and its targets are correct
before pushing them.

Locations of target repositories are calculated in the same way as when updating repositories.
Unlike the update command, this command does not have the `url` argument or the `--authenticate-test-repo`
flag among its inputs. Additionally, it allows specification of the firs commit which should be validated through the `--from-commit`
option. That means that we can only validate new authentication repository's commits. This
command does not store information about the last validated commit. See updater documentation
for more information about how it works.
Here are a few examples:

```bash
taf repo validate --path E:\\root\\namespace\\auth_repo
```

```bash
taf repo validate E:\\root\\namespace\\auth_repo --from-commit d0d0fafdc9a6b8c6dd8829635698ac75774b8eb3
```

```bash
taf repo validate
```

if repository is located inside the current working directory.

### `targets update-and-sign-targets`

Update target files corresponding to target repositories specified through the target type parameter
by writing the current top commit and branch name to target files corresponding to the listed repositories.
Sign the updated files and then commit. Types are expected to be defined in `reposoitories.json`,
as a part of custom data. This is expected to be generalized in the future since TAF should not
expect a certain custom property to exist. If types are not specified, update all repositories specified
in `repositories.json`.

All target repositories are expected to be inside the same root directory, but do not necessarily have
to be inside the same root directory as the authentication repository. However, if all of these
repositories are in the same root directory, this directory does not have to be specified and is calculated
as two directories up from the authentication repository's directory. Location of target repositories
is then determined by appending namespace prefixed name of a repository, as listed in `repositories.json`
to the root directory. For example, if `namespace1\repo1` is listed in `repositories.json` and
the root directory is `E:\OLL\example`, this command will expect `E:\OLL\example\namespace1\repo1` to contain a
target repository. The repository's current top commit and branch will then be written to the corresponding
target file - `targets\namespace\repo1`. Once all target files are updated (for each all repositories of
listed types, or all repositories listed in `repositories.json` if type is not provided), all corresponding target
metadata files, as well as snapshot and timestamp are automatically signed.

For example,

```bash
taf targets update-and-sign --path E:\\root\\namespace\\auth_repo --keystore E:\\keystore --target-type html
```

```bash
taf targets update-and-sign --keystore E:\\keystore --target-type html
```

If `path` option is omitted, the repository will be expected to be located inside the current working directory.

will update target files corresponding to target repositories whose `custom\type` attribute in `repositories.json`
is equal to `html`. NOTE - should be updated to be made more generic.

> **_NOTE:_**  This command should be used with caution and primarily while initializing an authentication
repository. If the target file contained additional data, that information will not be persisted. Make sure
that the target repositories are on the correct branch before running the command.

 TAF can be used to implement an automated process which will update all repositories in accordance with a specific project's needs.

```bash
taf targets update-and-sign --path E:\\root\\namespace\\auth_repo --keystore E:\\keystore
```

will sign all target repositories listed in `repositories.json`

### `targets sign`

This command registers target files and signs updated metadata. All targets
metadata files corresponding to roles responsible for updated target files are updated.
Let's say that we have the following target files:

- `targets`
  - `file1.txt`
  - `file2.txt`
  - `delegated_role1_dir`
    - `file1.txt`
    - `file2.txt`
    - `file3.txt`
  - `delegated_role2_dir`
    - `file1.txt`
    - `file3.txt`

and that files `targets/file1.txt` and `targets/delefated_role1_dir/file2.txt` were modified.
Assuming that the `targets` role is responsible for files directly inside the `targets`
directory and that `degetated_role1` is responsible for files in `delegated_role1` directory
and that `delegated_role2` is responsible for files in `delegated_role2`. This command
will update `targets.json` and `delegated_role1.json` metadata files by modifying information
about the updated targets. Once the targets metadata files are updated, so are `snapshot` and `timestamp`. Metadata files can be signed using the keystore files, Yubikeys or by directly entering keys. If one or more of the mentioned metadata files should be
signed with keys stored on disk, it's necessary to provide the keystore pat, by either using the `--keystore` option or providing a `--keys-description` json which contains the `keystore` property.

Unless `no-commit` flag is specified, changes will be committed automatically.

```bash
taf targets sign --path E:\\OLL\\auth_rpeo --keystore E:\\OLL\\keystore
```

If `path` option is omitted, the repository will be expected to be located inside the current working directory.


### `metadata update-expiration-dates`

This command updates expiration date of the given role's metadata file. The metadata file
can be signed by directly entering the key when prompted to do so, by loading the key
from disk or from a Yubikey. If key should be loaded from disk, it is necessary to specify
the keystore path using the `--keystore` option or by providing a `--keys-description` json which
contains the `keystore` property. The new expiration date is calculated by
adding interval to the start date, both of which can be specified when calling this command.
By default, start date is today's date, while interval depends on the role and is:

- 365 in case of root
- 90  in case of targets
- 7 in case of snapshot
- 1 in case of timestamp and all other roles

Unless `no-commit` flag is specified, changes will be committed automatically.

For example:

```bash
taf metadata update-expiration-dates --path E:\\OLL\\auth_rpeo --role targets1 --role targets2 --interval 5 --keystore E:\\OLL\\keystore
```

or

```bash
taf metadata update-expiration-dates --interval 5 --role targets1 --role targets2 --interval 5 --keystore E:\\OLL\\keystore
```

If `path` option is omitted, the repository will be expected to be located inside the current working directory.
At least one role needs to be specified. All metadata files that need to be updated in order to ensure the validity
of the repository will be updated automatically (snapshot and timestamp are updated after a targets role is updated, and
timestamp is updated after snapshot is updated).

This will set the new expiration date of the targets1 and targets2 roles to 5 days after the current date
and automatically commit the changes.

### dependencies add

A dependency is an authentication repository which has a parent-child relationship with another authentication repository.
When updating a parent authentication repository, its dependencies are recursively updated as well. Dependencies are
specified in a special target file called `dependencies.json`. In addition to storing names of dependencies, it is
necessary to also store a commit which can then be used for out-of-band validation, as well as the branch which contains
this commit (one commit can belong to multiple branches, so storing just commit sha is not sufficient). This out-of-band authentication commit represents a commit including and following which state of the authentication repository is expected to be valid at every revision. Someone who wants to host an authentication repository can contact the owner and confirm
the validity of this commit. If additional information that is not required by TAF should also be stored in `dependencies.json`,
it is specified by providing additional options when calling the command. Here is an example:

```bash
taf dependencies add --path auth-path namespace1/auth --branch-name main --out-of-band-commit d4d768da4e8f74f54c644923b7ed0e19a0faf3c5 --custom-property some-value --keystore keystore-path
```

In this case, custom-property: some-value will be added to the custom part of the dependency dependencies.json. If `path` option is
omitted, the repository will be expected to be located inside the current working directory.

If branch-name and out-of-band-commit are omitted, the default branch and its first commit will be written to dependencies.json.

Dependency does not have to exist on the filesystem, but if it does, provided branch name and out-of-band commit sha
will be validated, so it is recommended to run the updater first and update/clone and validate the dependency first.
If the dependency's full path is not provided, it is expected to be located in the same library root directory as the
authentication repository, in a directory whose name corresponds to its name. If dependency's parent authentication repository's
path is `E:\\examples\\root\\namespace\\auth`, and the dependency's namespace prefixed name is `namespace1\\auth`, the target's path
will be set to `E:\\examples\\root\\namespace1\\auth`.


### dependencies remove

To remove a dependency from dependencies.json, run

```bash
taf dependencies remove --path auth-path namespace1/auth --keystore keystore-path
```

This will also update and sign targets metadata, snapshot and timestamp using yubikeys or keys loaded from the specified keystore
location.  If `path` option is omitted, the repository will be expected to be located inside the current working directory.
