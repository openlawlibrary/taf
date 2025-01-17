# Repositories

As a tool focused on the creation and secure update of Git repositories (authentication repositories and their
targets), TAF contains classes and functions that strive to make integration with Git and TUF as simple as possible.
`GitRepository` acts as a wrapper around Git calls, enabling interaction with the actual `Git` repository on the file
system, e.g., creating a new branch, listing, creating, and pushing commits, etc. Conversely, the `MetadataRepository`
class in `tuf/repository.py` extends TUF's `Repository` class, an abstract class for metadata modifying implementations.
It provides implementations of crucial TUF concepts, such as adding a new delegated role, determining which role is
responsible for which target file, and adding TUF targets etc. An authentication repository can be seen as a Git
repository that is also a TUF repository. It contains TUF's metadata and target files and a `.git` folder. TAF's
`auth_repo` module's `AuthenticationRepository` class follows that logic and is derived from the two previously
mentioned base classes. Finally, `repositoriesdb` is a module inspired by TUF's modules like `keysdb`, which deals with
the instantiation of repositories and stores the created classes inside a "database" - a dictionary which maps
authentication repositories and their commits to lists of their target repositories at certain revisions. Note: the
concept of databases has been removed from TUF and removal of `repositoriesdb` is also planned in case of TAF.

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

## Implementation of TUF's `Repository` class (`tuf/repository/MetadataRepository`)

This class extends TUF's repository interface, providing features for executing metadata updates, such as
adding new signing keys, updating and signing metadata files, and extracting information about roles,
keys, delegations, and targets. It can be used to create a new TUF repository, retrieve information about
a TUF repository, or update its metadata files. TAF's implementation of the repository class follows the
convention of separating metadata and target files into directories named `metadata` and `target`:

```
- repo_root
  - metadata
    - root.json
  - targets
```

It is instantiated by providing the repository's path. Unlike the previous implementation, which was based on an
older version of TUF, this repository does not have, nor does it need, a name. The class can be instantiated
regardless of whether there are `metadata` files located at `path/metadata`. In fact, it is possible to read the
metadata and target files from mediums other than the local file system. TUF enables such flexibility by allowing
custom implementations of the `StorageBackendInterface`. These implementations can redefine how metadata and target
files are read and written. To instantiate a `MetadataRepository` class with a custom storage interface, use the
`storage` keyword argument. If not specified, TUF's default `FilesystemBackend` will be used. The other available
option is `GitStorageBackend`. This implementation loads data from a specific commit if the commit is specified,
or from the filesystem if the commit is `None`, by extending `FilesystemBackend`.

This class is used extensively to implement API functions.


## `AuthenticationRepository`

This class is derived from `GitRepository`, and indirectly from `MetadataRepository`. Authentication repositories are
expected to contain TUF metadata and target files, but are also Git repositories. It is important to note that only
files inside the `targets` folder are tracked and secured by TUF.


Instances of the `AuthenticationRepository` are created by passing the same arguments as to `GitRepository` (`library_dir`, `name`, `urls`, `custom`, `default_branch`, `allow_unsafe` and `path` which can replace `library_dir` and `name` combination), as well as some optional additional arguments:
- `conf_directory_root` - path to the directory where the `last_validated_commit` will be stored.
`last_validated_commit` is generated by the updater after a successful update and contains the last commit of
the authentication repository that was pulled and validated. Instead of validating the entire commit history when
re-running the update process, updater starts from `last_validated_commit`.
- `out_of_band_authentication` - manually specified initial commit, used during the update process to validate the first commit

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
