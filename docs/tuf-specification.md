# TUF Implementation

The Update Framework (TUF) helps developers secure new or existing software update systems, which are
often found to be vulnerable to many known attacks. Unlike other examples of TUF's usage, we:

- want to integrate TUF with Git and GitHub
- do not want to think of a single uploaded file (e.g. a xml or html file) as a target file and list all of them inside the targets metadata files,
- do want to think of Git commits as target objects.

The goal of this document is to explore how TUF can be used to protect GitHub repositories - which aspects need to be modified and how, and which must be closely followed.

A repository for experimentation and familiarization with TUF is [here](<https://github.com/openlawlibrary/tuf-test>).

## Security Models

TUF's integration with PyPI proposed two PEPs with two security models - minimum and maximum security.
This can also be applied to our case, so this section will give a very short overview of both of them.

**Minimum security model** states that an online key is used to sign all uploaded packages. This level
of security prevents a project from being accidentally or deliberately tampered with by a mirror or a
CDN, as they will not have the needed key required to sign the projects. However, an attacker who has
compromised the repository can manipulate TUF metadata using the stored key.

**The maximum security model** specifies that developers should sign their projects and upload the
signed metadata. If the repository infrastructure were to be compromised, the attackers would be unable
to serve malicious versions of the developer-signed project without access to the project's developer
key. The strength of this model is in these keys, as they are kept offline. There is much more to this
model, mostly regarding how just uploaded and older projects are protected, but that is not relevant to
our needs.

## Git

The core of Git is a key-value data store. Everything inserted into a Git repository is given a unique
key. All the content is stored as tree and blob objects - trees correspond to directories, blobs to file
contents. Git stores contents of a file for tracking history, named with the SHA-1 checksum and its
header. The subdirectory is named with the first 2 characters of the SHA-1, the filename is the
remaining 38 characters.  A commit is a snapshot of the project. It is associated with a snapshot tree,
which contains blob nodes for the files that have changed and includes information about its author, as
well as the parent commit.

A header is stored with every object committed to the Git object database. The header starts with the
identifier of the object's type (e.g. blob), followed by a space and the size in bytes of the contents.
Lastly, Git adds a null byte:

`blob 16\u0000`

Git then concatenates the header to the original content of the file and calculates the SHA-1 checksum
of the content. Afterwards, this new content is zipped and written to disk <a id="1return"></a>[^1](#1).

### Threats

In this section, possible security threats to a Git repository will be presented.

#### Collision attack

Git uses SHA-1 which is becoming problematic. It has been proven that Git is vulnerable to collision
attack. Collision means that two distinct objects have the same hash. Git can only store one half of the
colliding pair, and when following a link from one object to the colliding hash name, it can't know
which object the name was meant to point to. If a Git fetch or push tries to send a colliding object to
a repository that already contains the other half of the collision, Git detects this attempt. However,
the collision attack can be carried out through Git's mechanisms of signing commits or tags. A signed
commit or tag points to other objects containing the actual files by using their SHA-1 names. A
collision in those object could produce a signature which appears to be valid, but points to different
data than the signer intended. In such attacks the victim sees one half of the collision and the
attacker the other one.

GitHub already implemented prevention from this attack <a id="2return"></a>[^2](#2). Additionally, there are plans to migrate
Git from SHA-1 to a stronger hash  function <a id="3return"></a>[^3](#3).

#### Compromising a repository

Even though GitHub accounts are password protected, one cannot assume that they can never be
compromised. Similarly, we cannot be certain that GitHub itself won't get hacked, which would put
millions of projects at risk of being deleted or modified. In fact, there have been successful attacks
in the past where the attackers were able to gain access to a number of GitHub users' accounts <a id="4return"></a>[^4](#4), and
when they exploited certain GitHub's security holes and pushed commits to an arbitrary project's master
branch <a id="5return"></a>[^5](#5). By compromising GitHub account of one of the developers who can push to a repository, the
attacker can:

- upload a new GPG key to GitHub,
- push new commits to any of the oll or partners' repositories, including the authentications one, meaning that they can upload malicious files or replace TUF metadata files and/or online public keys,
- add another GitHub-authorized user with write access,
- unprotected the master branch of any of the repositories and force push to it.

An attacker can also gain access to someone's personal computer. The most common ways through which
hackers access a personal computer include sending emails which contain viruses and malware or links to
malicious sites, sending links to malicious sites via social networking sites, hijacking ads,
advertising malware as legitimate software and APTs (multi-pronged attempts to break in into a specific
organization's or institution's data network). An attacker can then install a keylogger and capture
every username and password typed on the keyboard <a id="6return"></a>[^6](#6).

In order to make it more difficult for an attacker to pretend to be someone else, GitHub can require
that commit signing is performed. Without it, it would be much easier for an attacker to pretend to be
one of the original authors. They would only need to set their Git username and email to that of one of
the developers. Similarly, signing tags provides a way of verifying the source of a release. However,
this alone is not enough, since a GPG key needs to be uploaded to GitHub <a id="7return"></a>[^7](#7). So, by compromising
GitHub account of one of the developers and uploading a new key, the attacker would be able to push
verifiable commits. That is why TUF must be used on top of Git and GitHub in order to increase security.

Currently, AppVeyor is used as our continuous integration system. Each time a commit is pushed or a pull
request is created, the AppVeyor CI runs tests and updates build status on GitHub. The AppVeyor
pre-merge script can be enhanced to also check TUF metadata and report a problem if there are potential
security issues detected.

### Conclusion

Since we are using Git, we do need to implement certain parts of TUF's specification. Namely, those
dealing with target files. We do not need to calculate hashes of files and do not have to worry about an
attacker changing contents of files. At least, not without pushing a new commit or modifying history. We
need to focus on checking if commits are valid. Simply relying on signatures is not enough, as the keys
need to be uploaded to a developer's GitHub account, which can be compromised. So, we'll slightly modify
TUF's target role, but follow its specification otherwise.

## TUF Repository and Metadata
'
The main idea is to avoid modifying TUF specification at all and find a workaround for specifying
repositories as targets.

Additionally, we want to support the potential need to store commits made to another set of
repositories, not owned by the same Publishing Entity. In such case, we'll reference commits pushed to the
authentication repository of the other Entity.

There should be one central authentication repository, containing metadata files. In addition, the
targets role can delegate full or partial trust to other roles. Delegating trust means that the targets
role indicates another role (that is, another set of keys and the threshold required for trust) is
trusted to sign target file metadata. Partial trust delegation is when the delegated role is only
trusted for some of the target files that the delegating role is trusted for. Currently, we have no need
for delegations.

### Roles

We will have the following roles:

- Root, which delegates trust to specific keys trusted for all other top-level roles used in the system.
- Targets, whose signature indicates which target files are trusted by clients.
- Snapshot, which signs a metadata file which includes information about the
latest version of all of the other metadata on the repository (excluding the timestamp file)
- Timestamp, as described by TUF. This role signs a timestamped statement containing the hash of the
snapshot file.

The root and targets metadata files should be signed by very secure, offline key, while snapshot and
timestamp can be signed with keys that are kept online.


### Repository content


A repository which will contain the TUF metadata files should be created. It should store the following
files and folders:
```
- metadata
  - root.json
  - targets.json,
  - snapshot.json
  - timestamp.json
- targets
  - jurisdiction
    - name-xml
    - name-xml-codified
    - name-html
    - name-docs
  - repositories.json
```

The `targets.json` file (or the metadata file of a delegated role) requires all targets of the
corresponding role to be listed and uniquely identified by their paths. Each path is relative to
the targets directory. The main idea behind this directory structure is the following:
- Commits are stored as content target files.
- For each repository, there is one entry in `targets.json`, which contains data about the file where
the commit is stored. The unique paths are of format `jurisdiction/repository_name`.
- URLs and other information about the repositories (apart from the most recent commit) are stored in
- `repositories.json`. This file is also listed as a target in `targets.json`.

By adding files as targets, we makes sure we can detect unauthorized modification of these files. If someone
changed any of the files, they would also need to update `targets.json` and sign it with an offline key.

We might also at one point need to reference commits from authentication repository of another
Publishing Entity. These commits would also be stored as content of target files, located inside the `targets/authentication`
directory. So, a path referencing an external repository could be: `authentication/dcmayorsoffice`.

In addition to the listed targets, there can be other target files, storing additional information needed
for validation of the repositories.

### Metadata files

#### root.json

This file specified trusted keys for other top level roles. The signature threshold of this file should be
higher than 1 and we want it to be signed using YubiKeys. In addition to `root.json`, TUF generates
`1.root.json`, `2.root.json`… So, once a new `root.json` is created, `version.root.json` is created as well.
This is important because a new root should be signed by a threshold of old keys and a threshold of new
keys, and the clients should be able to verify its authenticity. So, version N+1 of the root metadata
file must have been signed by: (1) a threshold of keys specified in the trusted root metadata file
(version N), and (2) a threshold of keys specified in the new root metadata file being validated
(version N+1). Since we are using Git, we can use Git history to find all prior versions of the root
metadata file, as opposed to creating these versions <a id="8return"></a>[^8](#8).

#### targets.json

We only need one targets role, so there is no need for delegations. Targets are files located in the
`targets` repository. `targets.json` lists hashes and sizes of target files. The next section will
provide more information about the targets we need. Just like `root.json`, this file should also be
signed using YubiKey.

#### snapshot.json

This file lists the version numbers of all metadata on the repository, excluding `timestamp.json`.
This information allows clients to know which metadata files have been updated and also prevents mix-and-match
attacks. We need to generate this file during AppVeyor builds, which means that it is not possible to
require an offline key. However, it is not possible to perform a malicious update unless targets is compromised
as well. [See key compromise analysis section of PEP on PyPi](https://github.com/theupdateframework/
pep-on-pypi-with-tuf#key-compromise-analysis)

#### timestamp.json

This file contains hash of the snapshot file. Its role is to prevent an adversary from replaying an
out-of-date signed metadata file whose signature has not yet expired.  We need to generate this file as well
during AppVeyor builds, meaning that it will be signed by an online key. Similarly to snapshot,
malicious update is not possible if targets key is not compromised.

### Target files

We require existance of certain target files, though there could be additional one. These include, as
noted above, one target file per repository and a target files containing information about the repositories.

If a target's path specified in `targets.json` (or target file of a delegated role) is `somejurisdiction/law-xml`, there should be a target file
named `law-xml`, located inside `somejurisdiction` directory inside `targets`. These files are expected
to be json files, containing at least the commit SHA. Here is an example of a target file containing a
commit SHA:

```json
{
    "commit": "4a55ac5822bc4504673dcba43ac1959213531474"
}
```
They can contain other information, as needed. These targets are used to validate target
repositories. In addition to them, the framework expects some special target files:
- `repositoires.json` (required)
- `mirrors.json` (recommended, required if URLs are not defined in `repositoires.json`, re)
- `depoendencies.json` (optional)
- `hosts.json` (optional)
- scripts (optional)

#### repositoires.json

`repositories.json` contains repositories' definitions. Each repository is identified by a namespace prefixed name which
should match the corresponding name in `targets.json`. The `urls` property is used to specify the repository's
locations. We want to supported definition of multiple URLs, which is why this property is a list. Alternatively, URLs can be defined using another special target file, called `mirrors.json` (more about it in the next paragraph). On top
of that, it is possible to define any additional information, via the `custom` property. This is an example
of the repositories definition file:

```json
 {
 	"repositories": {
 		"jurisdiction/law-xml": {
			"custom": {
				"type": "xml"
			},
 			"urls": ["https://github.com/jurisdiction/law-xml"]
 		},
 		"cityofsanmateo/law-html": {
			"custom": {
				"type": "html"
			},
 			"urls": ["https://github.com/jurisdiction/law-html"]
 		},
 		"cityofsanmateo/law-xml-codified": {
			"custom": {
				"type": "xml-codified"
			},
 			"urls": ["https://github.com/jurisdiction/law-xml-codified"]
 		}
 	}
 }
```

In this example, `custom` is used to define the repository's type, but it can store any data. It's value is
expected to be a dictionary.

#### mirrors.json

This target files is use to determine URLs of repositories based on their names (specified in the `namespace/name` format in `repositories.json`). Namespace is expected to correspond to GitHub
organization name, so names defined in `reposiotires.json` are seen as `org_name/repo_name`. If `mirrors.json` looks like this:

```
{
    "mirrors": [
        "http://github.com/{org_name}/{repo_name}",
        "http://github.com/{org_name}-backup/{repo_name}",
        "http://gitlab.com/{org_name}/{repo_name}"
    ]
}
```
and a repository's name is `jurisdiction/law-xml`, its URLs will be set to `["http://github.com/jurisdiction/law-xml", "http://github.com/jurisdiction-backup/law-xml", "http://gitlab.com/jurisdiction/law-xml"]`.
The framework will try to clone/pull the repository from GitHub the first URL, if that fails, try to use the second one etc. 

**It is recommended to use `mirrors.json` instead of defining `URLs` lists in `repositories.json`. The second way is only still supported in order maintain backwards compatibility.**

#### dependencies.json

Starting with version `0.9.0`, the updater supports definition of hierarchies of authentication repositories. This means that it is possible to define one repository as the root authentication repository and link it with one or more other authentication repositories. The updater will automatically pull the whole hierarchy and only declare the update of the root repository as successful if update of all linked repositories succeeded. This is an example of a `dependecies.json`:

```{
    "dependencies": {
        "jurisdiction1/law": {
            "out-of-band-authentication": "bfcbc7db7adc3f43291a64b0572b6b114e63e98a"
        },
        "jurisdiction2/law": {
            "out-of-band-authentication": "d7a6b796cffe53ad89b4504084402570b7d17f6b"
        }
    }
}
```
When updating the repository which contains this target file, the updater will also update `jurisdiction1/law` and `jurisdiction2/law`. Their URLs are also determined by using the `mirrors.json` file (the root repository's `mirrors.json`).

`out-of-band-authenticatio` is an optional property which, if defined, it is used to check if the repository's first commit matches this property's value. This is far from perfect security measure, but adds an additional layer or protection. The safest way would still be to contact the repositories' maintainers directly.


### hosts.json


This special target file is used to provide hosting information. It contains mappings of domains and authentication repositories whose content (or more precisely, content of whose target repositories) should be served through them. The framework does not actually
handle servers configuration - it just extracts host information from the `hosts.json` file and makes it easier to consume this data later on. This is an example of `hosts.json`:


```
{
   "some_domain.orgs": {
      "auth_repos": {
      "jurisdiction1/law": {}
      },
      "custom": {
         "subdomains": {
            "development": {},
            "preview: {},
         }
      }
   }
   "another_domain.orgs": {
      "auth_repos": {
      "jurisdiction2/law": {}
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

#### Scripts

Every authentication repository can contain target files inside `targets/scripts` folder which are expected to be Python scripts which will be executed after successful/failed update of that repository. Scripts can also be defined on a host level - will be executed after update of all repositories belonging to that host.

If a repository was successfully pulled and updated, `changed`, `succeeded` and
`completed` handlers will be called. If there were no new changes, `unchanged`,
`succeeded` and `completed` will be executed. If the update failed, `failed` and
`completed` handlers will be invoked. Scripts are linked to the mentioned events by being
put into a folder of the corresponding name in side `targets/scripts`. Each folder can
contain an arbitrary number of scripts and they will be called in alphabetical order.
Here is a sketch of the `scriprs` folder:
```
/scripts
    /repo
      /succeeded - every time a repo is successfully pulled
      /changed
      /unchanged
      /failed - every time a repo is not successfully pulled
      /completed  - like finally (called in both cases)
    /host
      /succeeded - once for each host, after host's repositories have been successfully pulled
      /changed
      /unchanged
      /failed - if one repository failed
      /completed  - like finally (called in both cases)
```

Each script is expected to return a json containing persistent and transient data. Persistent data will automatically be saved to a file called `persistent.json` after every execution and passed to the next script, while the transient data will be passed to the next script without being stored anywhere. In addition to transient and persistent data, scripts receive information about repositories (both the auth repo and its target repositories), as well as about the update.

### Creation and update of metadata files

This section briefly explains when and how the metadata files should be created and updated.

#### root metadata

`root.json` is the first metadata file to be created and signed, as it delegates trust to specific keys.
It should be updated every time a key is compromised or replaced for a different reason. TUF recommends
that `root.json` is signed every year, even if no keys were compromised. A good trusted copy of this file
should be shipped to a client using using an out-of-band process.

This metadata file will be stored online, in the authentication repository. Everyone who has the right
to pull from this repository will be able to acquire the `root.json` file and, through Git, all of its
prior versions. In order to be certain that the latest version of the `root.json` file is valid, or find
out the commit hash of a commit when the last known valid `root.json` was pushed, the interested party
should call the Publishing Entity.

To replace a compromised root key or any other top-level role key, the root role signs a new `root.json`
file that lists the updated trusted keys for the role. When replacing root keys, an application will
sign the new `root.json` file with:

1. a threshold of keys specified in the previous version of the trusted root metadata,
2. a threshold of keys specified in the new root metadata file being validated.

TUF specifies that every time such a change is required, the root.json file should be versioned. So, a
new version.root.json is to be created e.g. 1.root.json, 2.root.json etc.. As mentioned in one of the
previous sections, we will skip this step and rely on Git to acquire the previous version when necessary.

The client must be able to establish a trusted line of continuity to the latest set of keys, meaning
that they must be able to download intermediate root metadata files, until the latest one is
reached. Since we are using Git, we do not have to worry about this requirement.

#### targets

`targets.json` should be updated every time a commit is pushed to any of the protected repositories.
This file will only be updated offline and signed with YubiKey.

#### snapshot and timestamp metadata

`snapshot.json` (and therefore also `timestamp.json`) is updated after any of the other metadata files has
changed (apart from mirrors and timestamp). So, the need to update `snapshot.json` can happen when:

- a key is replaced (other than timestamp and mirrors),
- a metadata file has expired and a new one is therefore created and stored,
- `targets.json` is updated. In this case, `snapshot.json` should also be updated automatically.

`timestamp.json` must be updated automatically after snapshot.json is changed.

## Workflow

This section specifies what happens when a client wants to pull the newest updates. Once a client
downloads the latest valid metadata files, they should be permanently stored on their machine. The
client's copy of the authentication repository will be referred to as the "client's repository" and the
contained metadata files as "client's metadata".

It is assumed that the clients should have a copy of all Git repositories on their machines. So, both
authentication and target ones. The question here is how to know where that repository is on the
client's machine/where it needs to be created. We can do something inspired by GitHub for Windows - have
a default directory *Documents/oll* where all repositories are stored with the appropriate namespaces.

The update process should consist of the following steps:

1. Clone the authentication repository as a bare Git repository to a temporary location. A bare Git
repository contains no working or checked out copy of the source files and stores Git revision history
in the root folder, instead of in a *.git* subfolder. No checkout of HEAD is performed after the clone is
completed (implies -n clone option). "Checking out" commits (moving the head pointer) is not all that
simple when working with a bare repository, but it can be done. For example:

   `git update-ref refs/heads/test 03cf441018d1e01c3500e824e5d5cd50862ef752`

   `git symbolic-ref HEAD refs/heads/test`

2. Fetch the changes. Pull cannot be performed in case of bare repositories. So, use `git fetch --all`

3. The client's files cannot always just be updated to the newest version. If, for example, the root
changed several times (from `1.root.json` to `4.root.json`) in order to check the validity of the latest
file one must first update their `root.json` to `2.root. json`, then to `3.root.json`, and then to
`4.root.json`. In our case, we don't have these versioned files, but the idea is still the same - it is
necessary to gradually update `root.json`, with the only difference being that we'll have one `root.json`,
versioned using Git. Also, we want to be able to detect any problematic commits and stop there, without
proceeding with the update. We can first load the client's metadata files (the versions corresponding to
the client's current commit) and set HEAD of the cloned repository to the commit following the last
commit in the client's repository. If there were no new commits after the client's one, the process ends
as there is nothing to be updated.

4. The goal of this step is to check if the client's metadata files can be safely updated and detect
alarming inconsistencies if they exist. Initially, the content of the client's metadata files are copied
and named the current metadata files. Until the latest commit is reached, these steps are performed:

5. Perform various comparisons and security checks

   1. Compare the current `root.json` to the `root.json` of the current commit in the temporary repository.
If it has changed, it is checked if it is signed by a threshold of old and a threshold of new keys.  If
this and other security checks confirm that the file is valid, the current root metadata is updated
(this is done without modifying any of client's actual metadata files). TUF's reference implementation
can be used to perform the checks and update.

   2. Load `timestamp.json` of the current commit. Perform security checks. If there are no problems and
   the file changed compared to the current version, update the current `timestamp.json`.

   3. Load `snapshot.json` of the current commit. Perform security checks. If there are no problems and
   the file changed compared to the current version, update the current `snapshot.json`.

   4. Load `targets.json` of the current commit. Perform security checks. If there are no problem and the
   file changed, update the current version of the files. If a target is a reference to another entity's
   repository, do not perform any security check. The referenced repositories will also be protected by
   our system, so we can assume the validity of the data.

   5. If no security issues were detected, set the current metadata files to the versions corresponding
   to the current commit.

   6. Perform additional security checks, including:

      - checking signatures and version numbers of metadata files,
      - checking if the file changed even though it shouldn't have (e.g. `snapshot.json` wasn't updated,
      but `targets.json` was),
      - for targets metadata, it can be checked if the target commits exist.

   7. If a problem is detected in any of the sub steps, step 4 is prematurely ended.

   8. If there are no problems, the next commit becomes the current commit. If there are no more commits, step 4 is finished.

1. If there were no problems, the client's metadata files should be updated. We do not want to simply
copy the latest versions of these files from the temporary directory, as we want the client's
authentication repository to be synchronized with the remote repository (have complete Git history). So,
the following steps are taken:

   1. The changes are pulled from the remote repository, up to the last commit in the temporary
repository <a id="9return"></a>[^9](#9). If the client's repository doesn't exists, it needs to be cloned, and the
HEAD pointer of this repository should point to the same commit as the HEAD of the temporary repository.

   2. Another commit might have been pushed in the meantime, and we do not want to update the client's
   metadata files without checking the validity of that commit, nor do we want to keep repeating the
   validation process too many times. It might make sense to take into account the newest commits and
   perform the validation again once or twice - just in case the client started the update process at a
   very bad time. However, someone pushing non-stop to the authentication repository can only happen in
   case a malicious party has taken control over it.

   3. Keep the previous versions loaded, as we'll need them in the next step.

7. Once the metadata files are updated, it is safe to pull the actual updates:

   1. For each of the targets (repositories), check if there were any updates  Compare the commit hashes
of each of the targets of the previous version of the client's metadata file (before the update), to the
commit hashes contained by the new file.  If one or more of the repositories were updated, the changes
need to be pulled by the client. The case when there is no previous version of the metadata file is
treated the same as if it did exist and there were changes.
   2. For each of the updated repositories, we check if a local copy exists. If a repository does not
   exist, it needs to be cloned. So, we need to know the URL of the repository. This can easily be done
   by reading the URL based on the path from `repositories.json`. Path values in `targets.json` and
   `repositories.json`.
   should be the same. After cloning a repository, the HEAD needs to be set to the commit specified by
   the `targets.json` metadata file.
   3. If the repository already exists, we only need to pull the changes. The branch already has a
   remote tracking branch set, so no need to use the `repositories.json` file. Just pull the updates up to the
   commit specified by `targets.json`.
   4. In both cases, I don't think that it's necessary to check the validity of new/updated files since
   we're using Git. Git should check if hashes of files are correct etc. Also, git will automatically
   remove obsolete files, so no need to do this manually.
   5. If a target references another Entity's repository (which should be their TUF authentication
   repository), download the `targets.json`, as well as `repositories.json` from there, and use that information to clone or pull changes of the referenced repositories.
   6. If `repositories.json` changed, it is necessary to change Git origin.

## Compromises

If one or more of timestamp, snapshot or targets keys have been compromised, the following actions
should be taken according to TUF's specification:

1. Revoke timestamp, snapshot and targets keys from the root role, issue new ones.
2. Sign the new targets metadata file.
3. Compare the target (commits in our case) with the last known good snapshot, where no keys were known
to have been compromised. If there were additional commits pushed to any of the repositories, consider
reverting the changes.
4. Increment versions of metadata files, updated expiry times, sign them.
5. Issue new snapshot and timestamp.

If less than a threshold of root keys has been compromised, all of the compromised root keys must be
replaced. A new root.json is then issued and signed. The new root.json needs to be signed by both new
and old root keys, so that all clients can obtain the new version of this metadata file (which might
never happen). If a threshold number of root keys has been compromised, an end-user can choose to update
new root metadata using out-of-band mechanisms (they cannot verify the validity of the new file). In our
case, the planned out-of-band mechanism means calling the Publishing Entity and asking for a commit hash
of a commit in the authentication repository which is guaranteed to point to a valid and current root
metadata file.

After recovery from an attack is complete and new metadata files are created and signed, they are pushed
to the authentication repository. This commit is considered to be the new beginning of the
authentication chain.

## Issues

This section presents some additional problems we might need to think about.

### Manual pull

Even though the outlined workflow defines how the update process should be performed, there is nothing
preventing a user from running git pull on their machine and pulling malicious files. We could look into
writing a Git hook to prevent this. We will also need to somehow allow git pull (fetch and merge) to be
executed when we programmatically invoke them.

#### Git Hooks

Git hooks provide a way to fire off custom script when certain important actions occur <a id="10return"></a>[^10](#10). They can
be divided into client and server side groups, with client-side hooks being triggered by operations such
as committing and merging. All hooks are stored in the hooks subdirectory of the Git directory
(.git/hooks). After a repository is initialized, Git adds a number of example scripts, but additional
scripts can be easily added. For a script to be considered to be a Git hook, it needs to be properly
named (Git defines these names), without an extension, executable and placed inside the hooks directory.
It can be written in many different scripting languages, including Python, Shell, Perl…

[Here](https://gist.github.com/mwise/69ec35b646b52d98050d) is an example of a Git hook which prevents
merging staging branch into master. This example implements prepare-commit-msg hook. This hook is run
before the commit message editor is opened and after the default message is created. It is usually used
for commits where the default message is auto-generated, such as merge commits, squashed commits and
amended commits. This hook can only be used if fast-forward merges are disabled. [Another example](https://gist.github.com/hujuice/bddeffb378df37c17d93909180455ea0#file-prepare-commit-msg), inspired by
the first one. This hook prevents remote branches (other than remote master) from being merged into
local master.

I think that these examples (especially the second one) would make a very good starting point, if we
were to explore this option further. The end goal would be to prevent any remote branch from being
merged into local master when a user invokes pull. If a more complex branching model is implemented (a
different deployment strategy), we'll need to think about the other branches as well, and not just
master.

### Other branches

The update system should be implemented so that when a commit is pushed to an official branch, the
metadata files are updated. However, there can be many additional branches, since a developer needs to
be allowed to push new changes to a feature branch, which might later be merged via a pull request. So,
what if the following happens:

1. A user creates their own branch and pushes it to the remote repository.
2. An attacker adds a malicious file there.
3. The user does not notice this and makes a pull request which gets approved.
4. Valid metadata files are created, everything seems legit.

This problem can be addressed by making the system more complex. For example, we could create additional
roles and design metadata files. We could think of each branch as a “package”, and not repository of a
while. However, none of this is necessary if pull request aren't carelessly merged. Additionally, if a
repository is private and it's not possible for everyone to push to it, someone would first have to
compromise a developer's GitHub account or the repository itself, so they would then be free to do a lot
more damage than just push to a development branch.

### Detecting Security Problems

How will a repository compromise be detected? The clients will not be able to update their repositories
if there are security problems. But, in such cases, it is necessary to address those issue and recover
from an attack. Should we periodically check if an attack took place (check the metadata files)? This
should be automated and take place on a regular basis. Should the client's update system be able to
report an issue if it is detected?

## Useful links

1. [TUF Specification](https://github.com/theupdateframework/specification/blob/master/tuf-spec.md
   )
2. [Securing link from PyPI to end user](https://github.com/theupdateframework/pep-on-pypi-with-tuf
   )
3. [The Maximum Security Model]( https://www.python.org/dev/peps/pep-0480/
   )
4. [Overview of how TUF's referent implementation work](https://docs.google.com/document/d/1Seu8iRHLqctzjY7vfgsREoi78a8-j6sQaasYUtw2n2k/edit
   )
5. [Git internals](https://git-scm.com/book/en/v2/Git-Internals-Plumbing-and-Porcelain
   )

## Footnotes

<a id="1"/><a class="reference" href="#1return">^1</a>: Git Objects - Git SCM." <https://git-scm.com/book/id/v2/Git-Internals-Git-Objects>.

<a id="2"/><a class="reference" href="#2return">^2</a>: SHA-1 collision detection on GitHub.com · GitHub." 20 Mar. 2017, <https://github.com/blog/2338-sha-1-collision-detection-on-github-com>

<a id="3"/><a class="reference" href="#3return">^3</a>: git/hash-function-transition.txt at `master` · git/git · GitHub." 28 Sep. 2017, <https://github.com/git/git/blob/master/Documentation/technical/hash-function-transition.txt>

<a id="4"/><a class="reference" href="#4return">^4</a>: Github accounts Hacked in 'Password reuse attack' - The Hacker News." 16 Jun. 2016, [https://thehackernews.com/2016/06/github-password-hack.html](https://thehackernews.com/2016/06/github-password-hack.html)

<a id="5"/><a class="reference" href="#5return">^5</a>: How I hacked Github again | Hacker News." 8 Feb. 2014, <https://news.ycombinator.com/item?id=7197048>.

<a id="6"/><a class="reference" href="#6return">^6</a>: "How hackers access your computer | Blog BullGuard - Your Online ...." 27 Apr. 2015, <https://www.bullguard.com/blog/2015/04/how-hackers-access-your-computer.html?lang=en-IN>

<a id="7"/><a class="reference" href="#7return">^7</a>: Adding a new GPG key to your GitHub account - User ... - GitHub Help." <https://help.github.com/articles/adding-a-new-gpg-key-to-your-github-account/>.

<a id="8"/><a class="reference" href="#8return">^8</a>: git - List all commits for a specific file - Stack Overflow." <https://stackoverflow.com/questions/3701404/list-all-commits-for-a-specific-file>

<a id="9"/><a class="reference" href="#9return">^9</a>: "github - Git pull till a particular commit - Stack Overflow." [https://stackoverflow.com/questions/31462683/git-pull-till-a-particular-commi](https://stackoverflow.com/questions/31462683/git-pull-till-a-particular-commit)

<a id="10"/><a class="reference" href="#10return">^10</a>:  "Git Hooks - Git SCM." <https://git-scm.com/book/en/v2/Customizing-Git-Git-Hooks>.
