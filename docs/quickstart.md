# Quick Start

This documents describes the most useful commands. See [this overview](repo-creation-and-update-util.md) for more information.

## Create a repository

Use the `repo create` command to create a new authentication repository:

```bash
taf repo create repo_path --keystore keystore_path --keys-description keys.json --commit --test
```

- `keys-description` is a dictionary which contains information about the roles. The easiest way to specify it is to define it in a `.json` file and provide path to that file when calling the this command. For example:
```
{
  "roles": {
    "root": {
      "number": 3,
      "length": 2048,
      "passwords": ["password1", "password2", "password3"],
	    "threshold": 2,
      "yubikey": true
    },
    "targets": {
      "length": 2048,
      "delegations": {
        "delegated_role1": {
			    "paths": [
              "delegated_path1",
              "delegated_path2"
			      ],
			    "number": 1,
			    "threshold": 1,
			    "terminating": true
		    }
      }
    },
    "snapshot": {},
    "timestamp": {}
  },
  "keystore": "keystore_path"
}
```
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


## Update targets

To update authentication repository's target files based on the current state of the target repositories, use one of the two
`update_repos` commands. If `repositories.json` exists, use the `targets update_repos_from_repositories_json`
command. If that is not the case, call `targets update_repos_from_fs`. They both iterate through the
directory where target repositories are located. `update_repos_from_repositories_json` skips all repositories
which are not listed in `repositories.json`, while `update_repos_from_fs` only skips the authentication
repository if it is inside the same directory as the the target repositories.

```bash
taf targets update_repos_from_fs auth_path --root-dir root_dir_path --namespace namespace --add-branch
```

```bash
taf targets update_repos_from_repositories_json auth_path --root-dir root_dir_path --namespace namespace --add-branch
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
