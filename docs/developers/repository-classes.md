# Repositories

As a tool focused on creation and secure update of Git repositories (authentication repositories and their
targets), TAF contains classes and functions which strive to make integration with Git and TUF as easy as possible.
`GitRepository` can be seen as a wrapper around git calls which make it possible to interact with the actual `Git`
repository located on the file system. E.g. to create a new branch, list commits, push to the remote etc.
On the other hand, `Repository` class contained by the `repository_tool` module can instantiate a TUF repository,
provided that the directory passed to it contains metadata files expected to be found in such a repository. It also
implements important TUF concepts, such as adding a new delegated role, determine which role is responsible for which
target file, add TUF targets etc. An authentication repository can be seen as a Git repository which is also a TUF repository - it
contains TUF's metadata and target files and a `.git` folder. TAF's `auth_repo` module's `AuthenticationRepository`
class follows that logic and is derived from the two previously mentioned base classes. Finally, `repositoriesdb`
is a module inspired by TUF's modules like `keysdb`, which deals with instantiation of repositories and stores the
created classes inside a "database" - a dictionary which maps authentication repositories and their commits
to lists of their target repositories at certain revisions.

## GitRepository

This class is instantiated by passing in a location of a file system directory which is a valid Git directory. This
can be done in two ways:
- by providing `library_dir` (library's root) and the repository's name (in the `namespace/name` format) - expected by default
- by passing in full path to the directory

Library root is an important concept in TAF. All target repositories linked to an authentication repository through
the `repositories.json` target file are expected to be in the same root directory. The updater will automatically create
such a structure by appending namespace prefixed names defined in `repositories.json` to the library root. If
relying on automatic instantiation of repositories provided by TAF, it important to keep in mind that it will assume
that that is the case. Let's look a the following path:

`E:\\oll\library\testnamespace\repo1`

It can be divided into `E:\oll\library` and `testnamespace\repo1`, where the first part is the library root and the
second one is namespace prefixed name of the repository. ***Repository's name must be in the `namespace/name` format
and an error will be raised during instantiation if that is not the case***. So, a `GitRepository` class pointing
to the listed location can be created in the following two ways:

- `GitRepository('E:\\oll\library', 'testnamespace\repo1')`
- `GitRepository(path='E:\\oll\library\testnamespace\repo1')`

During instantiation, repo's path will be validated regardless of how it was specified. The validation is supposed to
prevent malicious attempts at accessing paths beyond the library root, which is particulatly important if executed
on a server where repository name could be coming from an untrusted source.


In addition to `library_dir`, `name` and `path`, `GitRepository` contains the following optional attributes:
- `urls` - a list of URLs from which  Git will attempt to clone the repository. They can be HTTPS or SSH URLs or
local file system paths. The order of items in this list is important since clone will try to use the first URL and
only try to clone from the second one if the first attempt is not successful etc.
- `default_branch` repository's default branch ("main" if not defined)
- `allow_unsafe`: a flag which allows a Git's security mechanism which prevents execution of Git commands if
the containing directory is owned by a different user to be ignored
- `custom` - a dictionary containing any additional information. None of this data is used by the framework.

Once a repository object is created, it can be used to execute various Git commands. Some of the methods are
implemented using [pygit2](https://www.pygit2.org/), some through sending commands using `subprocess`. Some examples functionalities
supported by this class include creating new branches, checking out branches, merging, committing, pushing to remote, pulling,
cloning, listing all commits on a branch, finding the top commit etc. `GitRepository` instances make it much easier
to interact with the underlying Git repository - without directly using a more complicated `pygit2` interface or
needing to write and execute Git cli calls. The following code snipped clones a repository, creates an empty commit
and pushes the changes:

```
repo = GitRepository('E:\\oll\library', 'testnamespace\repo1', urls=['https://github.com/openlawlibrary/testrepo'])
repo.clone()
repo.commit_empty('An example message')
repo.push()
```

## Repository tool's `Repository`

This class can be seen as a wrapper around a TUF repository, making it simple to execute important updates, like
adding new signing keys, updating and signing metadata files and extracting information about roles, keys,
delegations and targets. It is instantiated by passing file system path which corresponds to a directory containing
all files and folders that a TUF repository expects. That means that `metadata` and `targets` folders have to exist
and that a valid `root.json` file needs to be found inside `metadata`. So:
```
- repo_root
  - metadata
    - root.json
  - targets
```
Optionally, `name` attribute can also be specified during instantiation. It will be used to set name of the TUF's
repository instance. This value is set to `default` if not provided. If more than one repository is to be used
at the same time, it is important to set distinct names.

TUF repository is instantiated lazily the first time it is needed. This object is not meant to be used directly.
The main purpose of TAF's repository class is to group operations which enable valid update of TUF metadata and acquiring
information like can a key be used to sign a certain metadata file or finding roles that are linked with
the provided public key. To set up a new repository or add a new signing key, it is recommended to use the
`developer_tool` module since it contains full implementations of these complex functionalities. Functionalities
like updating targets and signing metadata or updating a metadata's expiration date are fully covered by repository
class's methods and can be used directly. These include:
- `update_timestamp_keystores`, `update_snapshot_keystores` (`update_rolename_keystores`) and `update_role_keystores` (for delegated roles)
-`update_timestamp_yubikeys`, `update_snapshot_yubikeys` (`update_rolename_yubikeys`) and `update_role_yubikeys` (for delegated roles)

If `added_targets_data` or `removed_targets_data` is passed in when calling these methods (only applicable to
`targets` and delegated target roles), information about target files will be updated and the corresponding metadata
file will be signed. Its expiration date will be updated too. If there is targets data or if the called method
corresponds to a non-targets role, the metadata file's expiration will still be updated and the file will be signed.


## `AuthenticationRepository`

This class is derived from both `GitRepository` and TAF's `Repository`. Authentication repositories are expected
to contain TUF metadata and target files, but are also Git repositories. It is important to note that only files
inside the `targets` folder are tracked and secured by TUF.

Instances of the `AuthenticationRepository` are created by passing the same arguments as to `GitRepository` (`library_dir`, `name`, `urls`, `custom`, `default_branch`, `allow_unsafe` and `path` which can replace `library_dir` and `name` combination), as well as some optional additional arguments:
- `conf_directory_root` - path to the directory where the `last_validated_commit` will be stored.
`last_validated_commit` is generated by the updater after a successful update and contains the last commit of
the authentication repository that was pulled and validated. Instead of validating the entire commit history when
re-running the update process, updater starts from `last_validated_commit`.
- `out_of_band_authentication` - manually specified initial commit, used during the update process to validate the first commit
- `hosts` -  host data, specified using the `hosts.json` file. Hosts of the current repo can be specified in its
parent's repo (meaning that this repo is listed in the parent's `dependencies.json`), or it can be specified in hosts.
json contained by the repo itself. If hosts data is defined in the parent, it can be propagated to the contained
repos.

While in TAF's `Repository` class target files have no special meaning (it is only important that their actual states
match the information listed in the corresponding metadata file), `AuthenticationRepository`'s target file consist
of files which have a special meaning to the framework (like `repositories.json`) and target files which are used
to validate target repositories. So, this class also contains methods which are specific to the authentication
repositories as defined in TAF, and not just to TUF or communication with Git. One such widely used method is
`sorted_commits_and_branches_per_repositories` return a dictionary consisting of branches and commits belonging to it
for every target repository. The other is `targets_at_revisions`, which returns contents of all target files at
revision corresponding to the specified commit.

## `repositoriesdb`

The purpose of this module is to automatically instantiate all target or linked authentication repositories given an authentication
repository and, optionally, a list of commits. When a repository is instantiated, it is added to a dictionary ("database") and can be accessed when needed.
The automatic creation of repositories relies on reading `repositories.json` and `targets.json` when instantiating
target repositories and `dependencies.json` when creating linked authentication repositories. If commits are not
specified, only the head of the specified authentication repository will be used. This is the most common use case as
it is rarely needed to instantiate repositories based on some older state of the relevant files.

By default, create objects will be of the `GitRepository` (targets) and `AuthenticationRepository` (linked
authentication repositories) types. It is possible to specify a different class, as long as it is derived from
`GitRepository`/`AuthenticationRepository`. If some target repository instance has to be a different derived class, it is possible to
pass in a factory function, which is expected to return an instance of a class that is derived from `GitRepository`/
`AuthenticationRepository`. Once repositories are created and added to dictionaries, they can be loaded using
different `get_repository` functions.

Here is an example of instantiating and retrieving target repositories:
```
import taf.repositoriesdb as repositoriesdb
from taf.auth_repo import AuthenticationRepository

# instantiate the authentication repository
auth_repo = AuthenticationRepository('E:\\oll\library', 'testnamespace\auth_repo')

# instantiate target repositories
# specify library_dir, while namespace prefixed name of each repository will be
# read from repositories.json
# also define the default branch of the target repositories if it is different than main
repositoriesdb.load_repositories(
  auth_repo,
  repo_classes=CustomRepo,
  library_dir=auth_repo.library_dir,
  default_branch="master"
)
# now get one repository that was previously loaded
repo1 = repositoriesdb.get_repository(auth_repo, "testnamespace/repo1")

```

Function `load_repositories` instantiates target repositories and inserts them into a dictionary. A specific
target repository can then acquired by calling get_repository. Furthermore, `get_repositories` can be used
to retrieve all target repositories given an authentication repo and, optionally, a commit.
`get_repositories_by_custom_data` is similar to `get_repository`, but it also expects repository's custom
data as a "query parameter".

Similarly to `load_repositories`, `load_dependencies` is used to instantiate linked authentication repositories
based on the content of `dependencies.json`. Created authentication repositories can then be retrieved
using `get_auth_repositories` and `get_auth_repository`.
