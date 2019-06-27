# Authentication repository creation and update utility

TAF provides a number of commands for creating and updating the authentication repositories.
Some of them focus on creation and initial setup of the repositories, while the others
provide an easy way of updating information about target repositories.

At the moment, creation of repositories does not support using YubiKeys. However,
if a key used to sign the metadata files is imported to a YubiKey, that YubiKey can
later be used for signing.

## Options

The commands have similar options, most complex of which will be described in more detail
in the following sections.

### `repo-path`

Location on disk of the authentication repository. If the command creates the repository, the
specified directory should not already exist.

### `targets-dir`

A local directory where the target repositories are located. All target repositories are expected
to be in the same directory and that directory should not contain any additional content. Below
is an example of a valid `targets-dir` path.

```
E:\OLL\repos\target_repos
|-- TargetRepository1
|-- TargetRepository2
|-- TargetRepository3
```

In this example, `TargetRepository1`, `TargetRepository2` and `TargetRepository3` are expected to be
git repositories. All of them will be threated as target repositories. A future improvement of the tool
could make this more flexible.

### `namespace`

Namespace of the target repositories. Names of the repositories are determined based on their paths
are equal to names of the last directories on those paths. The provided namespace is combined with the
determined repository name to form a name which is used to identify that repository in `repositories.json` and
to create a target file inside `targets` directory corresponding to the target repository. If a repository's
namespaced name is `namespace/TargetRepository`, a the target file will be called `TargetRepository` and
placed inside a `namespace` directory inside `targets`. Namespace can be left empty. In that case the
target file will be directly inside `targets`.

### `targets-rel-dir`

This option is used when generating `repositories.json`. More precisely, for determining the repository's
url. If a repository does not have a remote set, the url
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


### `keystore`

Location of the keystore files.

### `keys-description`

To make commands such as generation of keys and all other commands which require certain
information about them (e.g. passwords of the keystore files) easier to use, an option called
`keys-description` was introduced. It allows passing in a json, like the following one:

```
{
  "root": {
    "number": 3,
    "length": 2048,
    "passwords": ["password1", "password2", "password3"]
	  "threshold": 2
  },
  "targets": {
    "length": 2048
  },
  "snapshot": {},
  "timestamp": {}
}
```

So, for each metadata role (root, targets, snaphost, timestamp) there is a description of its keys.
Configurable properties include the following:
- `number` - total number of the role's keys
- `length` - length of the role's keys. Only needed when this json is used to generate keys.
- `passwords` - a list of passwords of the keystore files corresponding to the current role. The first
entry in the list is expected to specify the first key's password.
- `threshold` - role's keys threshold

Names of keys must follow a certain naming convention. That is,their names are composed of the role's name
and a counter (if there is more than one key). E.g. `root1`', `root2`, `targets1`, `targets2`, `snapshot` etc.

If a property is omitted from the specification, it will have the default value. The default values are:
- `number=1`
- `length=3072` Note: If the generated key should be moved to a YubiKey 4, this value must not exceed 2048
- `passwords=[]` Meaning that the keystore files will not be password protected by default.
- `threshold=1`

The `keys-description` option can either directly contain the described json, or be a path to a file
which contains it.

### `targets-key-slot` and `targets-key-pin`

At the moment, none of the commands require usage of YubiKeys. `targets` metadata file can be signed
by loading a `targets` key from disk. This is enough when creating test repositories. However,
if `targets` should be signed using a key stored on a YubiKey, it is necessary to provide the YubiKey's
slot and pin.

## Commands

### `generate_keys`

Generates and write rsa keypairs. Number of keys to generate per a metadata role, as well as their
lengths and passwords of the keystore files are specified using the `keys-description` parameter.

```
taf generate keys --keystore E:\OLL\keystore --keys-description E:\OLL\data\keys.json
```
The generated keys files will be saved to `E:\OLL\keystore`

### `create_repo`

This command can be used to generate the initial authentication repository. The initial version
of all metadata files are created, but no targets are added.

```
taf create_repo --repo-path E:\OLL\auth_repo --keystore E:\OLL\keystore --keys-description E:\OLL\data\keys.json
```

will generate a new authentication repository at `E:\OLL\auth_repo` and sign it with the keys
read from the specified keystore. Any of the keys are password protected, the password is read
from json specified using `--keys-description`.

### `add_target_repos`

Creates or updates target files. Given a directory where the target repositories are located,
traverses though all directories in that root directory, assuming that each child directory is
a target repository, and determines the current HEAD SHA. The found SHAs are saved to target files.

If the targets directory has the following content

 ```
E:\OLL\repos\target_repos\namespace
|-- TargetRepository1
|-- TargetRepository2
|-- TargetRepository3
```
and if the command is called as follows

```
taf add_target_repos  --repo-path E:\OLL\auth_repo --targets-dir E:\OLL\repos\target_repos\namespace --namespace namespace
```

three target files will be created or updated. The resulting directory structure will be as seen below:

```
E:\OLL\auth_repo
|-- targets
     |-- namespace
         |-- TargetsRepository1
         |-- TargetsRepository2
         |-- TargetsRepository3
```

Since namespace is specified, a directory of that name will be created inside the `targets` directory.
For each target repository, a target file of the same name is created and populated with the repository's
current head SHA. For example,

```
{
    "commit": "248f82dbd2a2ba3555d0803b0377c1065d5b03d9"
}
```

This command does not update the metadata files.

### `add_targets`

This command registers the target files. This assumes that the target files
were previously updated. It traverses through all files found inside the
`targets` directory and updates the `targets` metadata file based on their
content. Once `targets` file updated, so are `snapshot` and `timestamp`
