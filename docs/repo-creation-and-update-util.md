# Authentication repository creation and update utility

TAF provides a number of commands for creating and updating the authentication repositories.
Some of them focus on creation and initial setup of the repositories, while the others
provide an easy way of updating information about target repositories.

## Arguments

Most commands have just one required argument, and that is authentication repository's path.
All other input parameters have default values or can be calculated based on this path, like
root directory and namespace. Both absolute and relative paths can be used. To make the examples
clearer, paths in this documentation are absolute.

## Options

The commands have similar options, most complex of which will be described in more detail
in the following sections.

### `root-dir` and `namespace`

Root directory. All target repositories are expected to be inside this repository, either directly
or inside a directory which is directly inside the root directory. That is, if names of targets
are not namespace prefixed, they are expected to be directly inside the root directory. Otherwise,
it is assumed that they are in a directory whose name corresponds to their namespace. For example,
if root directory is `E:\example` and namespace of the target repositories is `namespace1`,
these repositories are expected to be in `E:\example\namespace1` directory.
Unless these two parameters are explicitly set, they are determined based on authentication
repository's path, which is a required argument of all commands that have `root-dir` and `namespace`
options. It is assumed that the authentication repository is also inside a namespace directory.
By default, namespace is set to the authentication repository's namespace and `root-dir` to
the namespace directory's parent directory. If authentication repository's path is
`E:\example\namespace2\auth-repo`, `namespace` is set to `namespace2` and `root-dir` to
`E:\example`. If any of these assumentions is not correct (authentication and target repositoris
do not have the same namespace authentication repository is at a completely different location),
it is necessary to set root directory and namespace manually throug h`root-dir` and `namespace`
options.

Full names of target repositories combine their namespace and name. These names
are used as keys in `repositories.json` and to create a target files inside `targets` directory
corresponding to the targets repository. If a repository's namespaced name is
`namespace/TargetRepository`, a the target file will be called `TargetRepository` and
placed inside `namespace` directory inside `targets`. Namespace can be left empty. In that case the
target file will be directly inside `targets`.

### `targets-rel-dir`

This option is used when generating `repositories.json`. More precisely, for determining the
repository's url. If a repository does not have a remote set, the url
which is to be saved in `repositories.json` is set based on the target repository's path on the filesystem.
If `targets-rel-dir` is specified, the url is calculated as the repository's path relative to this path.
It is useful when creating test repositories, when we do not want to use absolute paths. Since
`repositories.json` is also a target file, its content cannot just be modified prior to executing a test.

### `repos-custom`

`repositories.json` must contain a list of urls for each target repository and, optionally, additional
custom data. This option allows specification of that data. Similarly to `keys-description`, `repos-custom`
can either directly contain a valid json, or represent a path to a file which contains it. Since any data
can be inside `repositories.json`'s `custom` attribute, the mention json does not have to contain any
specific information. However, it is necessary to specify to which target repository the custom data
belongs to. With that in mind, here is an example of this option's value.

```
{
	"namespace/TargetRepo2": {
		"allow-unauthenticated-commits": true
	}
}
```
In this example it is specified that target repository `namespace/TargetRepo2` should have a custom property
called `allow-unauthenticated-commits` which is set to `true`.


### `keys-description`

To make commands such as creation of repositories, generation of keys and all others which
require certain information about roles and keys easier to use, an option called
`keys-description` was introduced. It allows passing in a json, like the following one:

{
	"roles": {
  	"root": {
  	  "number": 3,
			"threshold": 1
  	},
  	"targets": {
			"number": 1,
			"threshold": 1,
			"delegations": {
				"delegated_role1": {
					"paths": [
						"dir1/*"
						],
					"number": 3,
					"threshold": 2,
          "terminating": true
				},
				"delegated_role2":{
					"paths": [
						"dir2/*"
					],
					"delegations": {
						"inner_delegated_role": {
							"paths": [
								"dir2/inner_delegated_role.txt"
							],
              "terminating": true
						}
					}
				}
			}
  	},
  	"snapshot": {
			"scheme": "rsassa-pss-sha256"
		},
  	"timestamp": {
			"scheme": "rsassa-pss-sha256"
		}
	},
	"keystore": "keystore_path"
}

NOTE: in this example, scheme of snapshot and timestamp roles was specified in order to provide
and example of how to do so. At the moment, all keys should have the same signing scheme, so
make sure that you do not set different schemes. The default scheme is `"rsa-pkcs1v15-sha256`.

- `roles` contains information about roles and their keys, including delegations:
  -  `number` - total number of the role's keys
  - `length` - length of the role's keys. Only needed when this json is used to generate keys.
  - `passwords` - a list of passwords of the keystore files corresponding to the current role The first entry in the list is expected to specify the first key's password.
  - `threshold` - role's keys threshold
  - `yubikey` - a flag which signalizes that the keys should be on YubiKeys
  - `scheme` - signing scheme
  - `delegations` and `paths` - delegated roles of a targets role. For each delegated role, it is necessary to specify `paths`. That is, files or directories that the delegated role can sign. Paths are specified using glob expressions. In addition to paths, it is possible to specify the same properties of delegated roles as of main roles (number or keys, threshold, delegations etc.).
  - `terminating` - specifies if a delegated role is terminating (as defined in TUF - if a role is trusted with a certain file which is not found in that role an exceptions is raised if terminating is `True`. Affects the updater).
- `keystore` - location of the keystore files. This path can also be specified through an input parameter.

Names of keys must follow a certain naming convention. That is,their names are composed of the role's name
and a counter (if there is more than one key). E.g. `root1`', `root2`, `targets1`, `targets2`, `snapshot` etc.

If a property is omitted from the specification, it will have the default value. The default values are:
- `number=1`
- `length=3072` Note: If the generated key should be moved to a YubiKey 4, this value must not exceed 2048
- `passwords=[]` Meaning that the keystore files will not be password protected by default.
- `threshold=1`
- `scheme=rsa-pkcs1v15-sha256`

The `keys-description` option can either directly contain the described json, or be a path to a file
which contains it.
In cases when this dictionary is not specified, it is necessary to enter the needed
information when asked to do so, or confirm that default values should be used.

### `scheme`

Many commands have the `scheme` optional parameter. It represents the signature scheme.
`rsa-pkcs1v15-sha256` is used by default.

## Commands

Commands are separated into several subcommands:
- `keystore`, containing commands for generating keystore files.
- `metadata`, containing commands for adding a new signing key and updating a metadata file's expiration date.
- `repo`, containing commands for creating and updating new authentication repositories.
- `targets`, containing commands for updating target files (files in the `targets` directory of the authentication repository), as well for signing `targets.json` metadata file.
- `yubikey`, containing commands for setting up a new Yubikey and exporting public keys from Yubikeys

Here are some of the most important commands. Use the `--help` flag to see more information
about the commands. E.g. `taf repo create --help`.

### `keystore generate_keys`

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
taf repo create E:\\OLL\\auth_repo_path --keystore E:\\OLL\\keystore --keys-description E:\\OLL\\data\\keys.json --commit --test
```

will generate a new authentication repository at `E:\OLL\auth_repo_path`. There are several options
for signing metadata files - from keystore, by directly entering the key when prompted and by using
Yubikeys. If one or more keys are stored in the keystore, keystore path should be specified
when calling this command. If `keystore` is specified in `keys-description`, it is not necessary
to also use the `--keystore` option. All keys that do not already exist will be generated during
execution of this command. Keys can generated on the Yubikeys, but that will delete everything
stored on that key and will require new pins to be set. It is possible to reuse existing keys
stored on Yubikeys.

The generated files and folders will automatically be committed if `--commit` flag is present. If the
new repository is only be meant to be used for testing, use `--test` flag. This will create a special
target file called `test-auth-repo`.


### `repo update`

Update and validate local authentication repository and target repositories. Remote
authentication's repository url and its filesystem path need to be specified when calling this command. If the
authentication repository and the target repositories are in the same root directory,
locations of the target repositories are calculated based on the authentication repository's
path. If that is not the case, it is necessary to redefine this default value using the
`--clients-root-dir` option.
Names of target repositories (as defined in repositories.json) are appended to the root
path thus defining the location of each target repository. If names of target repositories
are namespace/repo1, namespace/repo2 etc and the root directory is E:\\root, path of the target
repositories will be calculated as `E:\\root\\namespace\\repo1`, `E:\\root\\namespace\\root2` etc.

When updating a test repository (that has the "test" target file), use `--authenticate-test-repo`
flag. An error will be raised if this flag is omitted in the mentioned case. Do not use this
flag when validating non-test repository as that will also result in an error.

For example:

```bash
taf repo update https://github.com/orgname/auth-repo E:\\root\\namespace\\auth_repo  --authenticate-test-repo
```

In this example, all target repositories will be expected to be in `E:\root`.

```
taf repo update https://github.com/orgname/auth-repo E:\\root\\namespace\\auth_repo --clients-root-dir E:\\target-repos
```

In this example, the target repositories will be expected to be in `E:\\target-repos`.

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
Unlike the update command, this command does not have the `url` argument or the `--authenticate-test-repoparameter` flag among its inputs. Additionally,
it allows specification of the firs commit which should be validated through the `--from-commit`
option. That means that we can only validate new authentication repository's commits. This
command does not store information about the last validated commit. See updater documentation
for more information about how it works.
Here are a few examples:

```bash
taf repo validate E:\\root\\namespace\\auth_repo
```

```bash
taf repo validate E:\\root\\namespace\\auth_repo --from-commit d0d0fafdc9a6b8c6dd8829635698ac75774b8eb3
```

### `targets update_repos_from_fs`

Update target files corresponding to target repositories by traversing through the root
directory. Does not automatically sign the metadata files.
Note: if `repositories.json` exists, it is better to call update_repos_from_repositories_json

Target repositories are expected to be inside a directory whose name is equal to the specified
namespace and which is located inside the root directory. If root directory is `E:\examples\\root`
and namespace is namespace1, target repositories should be in `E:\examples\root\namespace1`.
If the authentication repository and the target repositories are in the same root directory and
the authentication repository is also directly inside a namespace directory, then the commoroot
directory is calculated as two repositories up from the authetication repository's directory.
Authentication repository's namespace can, but does not have to be equal to the namespace or target,
repositories. If the authentication repository's path is `E:\root\namespace\auth-repo`, root
directory will be determined as `E:\root`. If this default value is not correct, it can be redefined
through the `--root-dir` option. If the --namespace option's value is not provided, it is assumed
that the namespace of target repositories is equal to the authentication repository's namespace,
determined based on the repository's path. E.g. Namespace of `E:\root\namespace2\auth-repo`
is `namespace2`.

Once the directory containing all target directories is determined, it is traversed through all
git repositories in that directory, apart from the authentication repository if it is found.
For each found repository the current top commit and branch (if called with the
--add-branch flag) are written to the corresponding target files. Target files are files
inside the authentication repository's target directory. For example, for a target repository
namespace1/target1, a file called target1 is created inside the `targets/namespace` authentication repository's directory.

For example, let's say that we have the following repositories:

 ```
E:\OLL\example\namespace
|-- TargetRepository1
|-- TargetRepository2
|-- TargetRepository3
|-- AuthenticationRepository
```

If we call the command as follows

```bash
taf targets update_repos_from_fs E:\\OLL\\examples\\auth_repo --add-branch
```

there is no need to directly set `namespace` and `root-dir` and  three target files will be created or
updated. The resulting directory structure will be as seen below:

```
E:\OLL\example\namespace\AuthenticationRepository
|-- targets
     |-- namespace
         |-- TargetsRepository1
         |-- TargetsRepository2
         |-- TargetsRepository3
```

A directory named after the repositories' namespace will be created inside the `targets` directory.
For each target repository, a target file of the same name is created and populated with the
repository's current head SHA. For example,

```
{
    "commit": "248f82dbd2a2ba3555d0803b0377c1065d5b03d9",
    "branch": "branch1"
}
```

On the other hand, if we have a directory structure like this:

 ```
E:\OLL\example
    |--namespace1
        |-- TargetRepository1
        |-- TargetRepository2
        |-- TargetRepository3
    |--namespace2
        |-- AuthenticationRepository
```

to get the same end result as in the previous case, the command would be called like this:

```bash
taf targets update_repos_from_fs E:\\OLL\\examples\\auth_repo --namespace namespace1 --add-branch
```

That is because the authentication repository and the target repositories share are in the same
root directory, but do not have the same namespace.

### `targets update_repos_from_repositories_json`

This command is very similar to the previous command, but it will only update target files
corresponding to repositories which are listed in `repositories.json`.

It is recommended to use this command if `repositories.json` exists.

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
signed with keys stored on disk, it's necessary to provide the keystore pat, by either using the `keystore` option or providing a `keys-description` json which contains the `keystore` property.

If the changes should be committed automatically, use the `commit` flag.

```bash
taf targets sign E:\\OLL\\auth_rpeo --keystore E:\\OLL\\keystore --commit
```

### `metadata update_expiration_date`

This command updates expiration date of the given role's metadata file. The metadata file
can be signed by directly entering the key when prompted to do so, by loading the key
from disk or from a Yubikey. If key should be loaded from disk, it is necessary to specify
the keystore path using the `keystore` option or by providing a `keys-description` json which
contains the `keystore` property. The new expiration date is calculated by
adding interval to the start date, both of which can be specified when calling this command.
By default, start date is today's date, while interval depends on the role and is:

- 365 in case of root
- 90  in case of targets
- 7 in case of shapshot
- 1 in case of timestamp and all other roles

If the changes should be automatically committed, use the `commit` flag.

For example:

```bash
taf metadata update_expiration_date E:\\OLL\\auth_rpeo snapshot --interval 5 --commit
```
This will set the new expiration date of the snapshot role to 5 days after the current date
and automatically commit the changes.
