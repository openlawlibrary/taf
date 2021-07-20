# Quick Start

This documents describes the most useful commands. See [this overview](repo-creation-and-update-util.md) for more information.

## `keys-description`

`keys-description` is a dictionary which contains information about the roles and their keys. The easiest way to specify it is to define it in a `.json` file and provide path to that file when calling various commands. For example:

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
an example of how to do so. At the moment, all keys should have the same signing scheme.
The default scheme is `"rsa-pkcs1v15-sha256`. Delegated target roles are optional - if all target files
should be signed using the `targets` key, there is no point in defining delegated target roles.

- `roles` contains information about roles and their keys, including delegations:
  -  `number` - total number of the role's keys
  - `length` - length of the role's keys. Only needed when this json is used to generate keys.
  - `passwords` - a list of passwords of the keystore files corresponding to the current role The first entry in the list is expected to specify the first key's password.
  - `threshold` - role's keys threshold - with how many different keys must a metadata files be signed
  - `yubikey` - a flag which signalizes that the keys should be on YubiKeys
  - `scheme` - signing scheme
  - `delegations` and `paths` - delegated roles of a targets role. For each delegated role, it is necessary to specify `paths`. That is, files or directories that the delegated role can sign. Paths are specified using glob expressions. In addition to paths, it is possible to specify the same properties of delegated roles as of main roles (number or keys, threshold, delegations etc.).
  - `terminating` - specifies if a delegated role is terminating (as defined in TUF - if a role is trusted with a certain file which is not found in that role an exceptions is raised if terminating is `True`. Affects the updater).
- `keystore` - location of the keystore files. This path can also be specified through an input parameter. This is the location where the keys will be saved to when being generated and where they will be read from when signing metadata files.

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
taf repo create repo_path --keystore keystore_path --keys-description keys-description.json --commit --test
```

- `repo-path` is the only argument and is required. It should point to a folder where the new authentication repository's content should be stored to e.g. `test/law`.
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

To update authentication repository's target files based on the current state of the target repositories, use one of the two
`update-repos` commands. If `repositories.json` exists, use the `targets update-repos-from-repositories-json`
command. If that is not the case, call `targets update-repos-from-fs`. They both iterate through the
directory where target repositories are located. `update-repos-from-repositories-json` skips all repositories
which are not listed in `repositories.json`, while `update-repos-from-fs` only skips the authentication
repository if it is inside the same directory as the the target repositories.

```bash
taf targets update-repos-from-fs auth_path --root-dir library_dir_path --namespace namespace --add-branch
```

```bash
taf targets update-repos-from-repositories-json auth_path --root-dir library_dir_path --namespace namespace --add-branch
```

- `root-dir` is the directory which contains the target repositories. Its default value is set to two
directory's up from the authentication repository's path
- `namespace` corresponds to the name of the directory inside `root-dir` which directly contains target
repositories. Its default value is name of the authentication repository's parent directory.
- `add-branch` is a flag which determines if name of the current branch of the target repositories
will be noted in the corresponding target file.

If the authentication repository and the target repositories are inside the same directory, there is
no need to set `root-dir` and `namespace`. This command does not automatically sign metadata files.

## Sign metadata files

To sign updated `targets` metadata file call the `targets sign` command. It updates all targets
metadata files corresponding to roles responsible for modified target files, `snapshot`
and `timestamp.json`

```bash
taf targets sign auth_path --keys-description keys_description.json --commit
```

- `keys-description` is the previously described dictionary containing information about roles, keys and optionally keystore location. If one or more keys should be loaded from the disk their location can be determined based on `keystore` property of this json.
- `keystore` defines location of the keystore files and should be used when keystore location is not specified in `keys-description` or when not using `keys-description` option, but one or more keys should be loaded from the disk.
- `commit` flag determines if the changes should be automatically committed
