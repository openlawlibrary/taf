# Setting up a new library

This document describes how to create a new authentication repository with all of the necessary content. The first step if to create an initialization file.

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

`taf yubikey setup_signing_key`

WARNING: This command will delete the YubiKey's existing data. New repositories can be created using already set
up YubiKeys.

## Create a repository

Use the `repo create` command to create a new authentication repository:

```bash
taf repo create auth_path --keystore keystore_path --keys-description keys-description.json --commit --test
```

- `auth-path` is the only argument and is required. It should point to a folder where the new authentication repository's content should be stored to e.g. `test/auth_repo`.
- `keys-description` is the previously described dictionary containing information about roles, keys and optionally keystore location. If one or more keys should be loaded from the disk their location can be determined based on `keystore` property of this json.
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

## Set up a remote repositories

Create new repositories in your GitHub organization - an authentication repository and one for each target repository.
DO NOT ADD THE INITIAL FILES when creating authentication repository's remote repository. The first commit should contain initial metadata files. If something is added
to the targe repositories, thus creating the initial commit, do not commit anything else before signing the initial commit. Set remote of the locally created authentication repository, commit initial metadata and target files and push them. E.g:

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

This target files is optional, but needs to be defined if the authentication repository references other authentication repositories (to define hierarchies), to make a use of the out-of-band authentication check and/or if the framework
is to be used to handle information about the hosts.

This is an example where there are no hierarchies, but we want to define the current repository's expected commit and want to make use of the hosts handlers.

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


### `hosts.json`

This is an optional file used to specify information about the hosts. The framework will only extract this information
from the file and does not implement anything related configuring the servers. Here is an example of this file:


```
{
   "some_domain.org": {
      "auth_repos": {
      	"test/auth_repo": {}
      },
      "custom": {
         "subdomains": {
            "development": {},
            "preview: {},
         }
      }
   }
}
```

## Sign added targets

After updating target files, it is necessary to sign them. That means updating and signing
the metadata files. This can be accomplished by calling the `targets sign` command. It updates all targets
metadata files corresponding to roles responsible for modified target files, `snapshot`
and `timestamp.json`

```bash
taf targets sign auth_path --keys-description keys_description.json --commit
```

- `keys-description` is the previously described dictionary containing information about roles, keys and optionally keystore location. If one or more keys should be loaded from the disk their location can be determined based on `keystore` property of this json.
- `keystore` defines location of the keystore files and should be used when keystore location is not specified in `keys-description` or when not using `keys-description` option, but one or more keys should be loaded from the disk.
- `commit` flag determines if the changes should be automatically committed

Commit and push the changes. Having pushed the changes, run local validation to be sure that the authentication repository is in a valid state:

```bash
taf repo validate auth_path
```

If hosts were defined, make sure that there is not message saying that that is not the case - that can suggest that names of the repositories defined in different files do not match.

## Add targets corresponding to target repositories

Next, register the target repositories by creating target files corresponding to target repositories. This can be done manually, but the easiest way to add initial target files and
update them is to use another one of available commands. Make sure that the filesystem structure matches the state defined in `repositories.json` - that each target repository is
in `library-dir/namespace/repo_name`. The authentication repository should also be in the same parent directory (`library-dir/namespace`).

Once that is all set up, make the planned changes and commit them. Unless `allow-unauthenticated-commits` is set to `true` in `repositories.json` for a target repository,
it is necessary to update the corresponding target files of the authentication repository after every commit.

WARNING: If you added initial REDME or lincese using the GitHub interface, register thos commits before making further changes.

Next, create or update the target files by running:

`taf targets update-repos-from-repositories-json auth_repo_path --add-branch`

This command will analyze `repositories.json`, determine path of all target repositories,
determine their latest commits and create target files in the auth repo matching the format that the updater expects. Verify that everything looks good and sign the target files by running. If all repositroies are in the same library root directory and have the same namsepace, there is no need to specify additional options. A complete list of options contains:

- `library-dir` is the directory which contains the target repositories. Its default value is set to two
directory's up from the authentication repository's path.
- `namespace` corresponds to the name of the directory inside `library-dir` which directly contains target
repositories. Its default value is name of the authentication repository's parent directory.
- `add-branch` is a flag which determines if name of the current branch of the target repositories
will be noted in the corresponding target file.

Push all changes made to both the authentication repository and the target repositories.

## Run the updater

Run the updater to make sure that everything has been set up correctly. If errors occur, you
might have not pushed everything. Read the update log and make sure that every repository
was recognized as a target repository (that the names and ulrs are correct throughout the
special target files). The updater will create a direcotry called `_auth_repo_name` in the
library root directory and write the last validated commit in a file directly inside it.

**To trigger validation from the first commit should that sound useful, delete this directory**

The updater will check out the last validated commits, so to continue working, checkout the default branch again.

For more information about the updater and how to use it, see [the update process document](./updater/update_process.md)

## Update metadata files if they expired

*This will be rework to make the update process easeir. An automate job can be set up to sign the metadata files. For testing purposes, sign them once and set a really long inteval*

By default, timestamp needs to be resigned every day, while snapshot expires a week after being signed. The updater will raise an error if the top metadata file has expired. To resign a metadata files, run:

```bash
taf metadata update-expiration-date auth_repo_path metadata_name --keystore keystore_path --interval days
```

- `metadata_name` represents a metadata file - root, targets, snapshot, timestamp, delegated_targets_role
- `keystore path` is the location of the keystore files. Can be ommitted if YubiKeys should be used instead
- `interval` refers to the number of days added to today's date to calculate the expiration date

**The order in which the files are signed is important**

### timestamp update


```bash
taf metadata update-expiration-date auth_repo_path timestamp --keystore keystore_path --interval days
```

### snapshot update


```bash
taf metadata update-expiration-date auth_repo_path snapshot --keystore keystore_path --inteval days
```

```bash
taf metadata update-expiration-date auth_repo_path timestamp --keystore keystore_path --inteval days
```

### targets update


```bash
taf metadata update-expiration-date auth_repo_path targets --keystore keystore_path --inteval days
```

```bash
taf metadata update-expiration-date auth_repo_path snapshot --keystore keystore_path --inteval days
```

```bash
taf metadata update-expiration-date auth_repo_path timestamp --keystore keystore_path --inteval days
```

**Don't forget to commit and push the changes**

