# Quick Start

This documents describes the most useful commands. See [this overview](repo-creation-and-update-util.md) for more information.

## Create a repository

Use the `repo create` command to reate a new authetnication repository:

```bash
taf repo create repo_path --keystore keystore_path --keys-description keys.json --commit --test
```

- `keystore` is the location of the keystore files. Use this options if the keystore files were previously
generated and not all metadata files should be signed using Yubikeys.
- `keys-description` is the a dictionary which contains information about the roles. The easiest way to specify
it is to define it in a `.json` file and provide path to that file when calling the `create command`. For example:
```
{
  "root": {
    "number": 3,
    "length": 2048,
    "passwords": ["password1", "password2", "password3"]
	  "threshold": 2,
    "yubikey": true
  },
  "targets": {
    "length": 2048
  },
  "snapshot": {},
  "timestamp": {}
}
```
- `commit` flag determines if the changes should be automatically committed
- `test`  flag determines if a special target file called `test-auth-repo` will be created. That
signalizes that an authentication repository is a test repository. When calling the updater,
it's necessary to use a flag which makes it clear that it is a test repository which is to
be updated.


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

- `root-dir` is the directory which contains the target repositories. It's default value is set to to
directory's up from the authentication repository's path
- `namespace` correspons to the name of the directory inside `root-dir` which directly contains target
repositories. Its default value is name of the authentication repository's parent directory.
- `add-branch` is a flag which determines if name of the current branch of the target repositories
will be noted in the corresponding target file.

If the authentication repository and the target repositories are inside the same directory, there is
no need to set `root-dir` and `namespace`. This command does not automatically sign metadata files.

## Sign metadata files

To signs updated `targets` metadata file call the `targets sign` command. Updates `targets`, `snapshot`
and `timestamp.json`

```bash
taf targets sign auth_path --keystore keystore_path --commit
```
- `keystore` is the location of the keystore files. Use this option if one or more files shoudl be signed
with keys loaded from disk.
- `commit` flag determines if the changes should be automatically committed
