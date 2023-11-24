# TAF specification

Nov 24, 2023

Version 0.1-alpha

## 1 Introduction

### 1.1 Scope

This document describes TAF, a framework that aims to provide archival authentication and
ensure that Git repositories can be securely cloned and updated. Built on top of
The Update Framework (TUF), TAF leverages TUF's security capabilities to protect Git repositories.
While TAF does not enhance the security properties of Git or code hosting
platforms like GitHub, it recognizes their vulnerabilities and provides mechanisms to detect attacks.
Additionally, TAF provides a suite of tools designed to facilitate the
initial setup and ongoing update of metadata in compliance with TUF specifications, as well
as the management of the relevant information about the Git repositories under its
protection.

The keywords "MUST," "MUST NOT," "REQUIRED," "SHALL," "SHALL NOT," "SHOULD," "SHOULD NOT,"
"RECOMMENDED," "MAY," and "OPTIONAL" in this document are to be interpreted as described in [RFC 2119](https://datatracker.ietf.org/doc/html/rfc2119).

### 1.2 Motivation

In the current landscape of rapid digital transformation, a trend significantly accelerated
by the global pandemic but with origins well before 2020, ensuring the integrity and
accessibility of electronically stored documents is a pressing matter. The initial
motivation for developing TAF was its application in protecting Git repositories that store
legal documents, aiming to guarantee their long-term availability and authenticity.
However, TAF is designed to be agnostic of the content it protects, as long as that content is stored in Git repositories.

In scenarios where maintaining a complete history of changes is essential, Git emerges as a
suitable choice. It was specifically designed to facilitate easy access to and comparison
of older versions of committed data. Git also focuses on providing tools to ensure the
integrity and authorship of code. A notable feature is the ability to sign commits and tags
with a GPG key. This signature mechanism serves as a verification that the commit was made
by the individual holding the corresponding private key, thus authenticating the authorship
of the commit. Additionally, Git offers robust access control mechanisms, particularly when integrated
with hosting platforms such as GitHub, GitLab, or Bitbucket. These platforms enable
repository owners to set permissions controlling who can read from or write to a
repository, effectively protecting the codebase against unauthorized alterations.

However, Git's approach to commit signing does place the burden of key management on the
user. This can leave open several potential attack vectors. For instance, an attacker could
compromise a user account on a hosting platform, breach the platform's security directly,
or gain unauthorized access to a developer's personal computer. In such scenarios, the
attacker might be capable of uploading a new GPG key to a platform like GitHub, pushing
malicious commits, altering user permissions, or even rewriting the repository's history
through force-pushes. These vulnerabilities highlight the need for additional security
measures beyond what Git and hosting platforms offer.

Furthermore, ongoing concerns about Git's reliance on the SHA-1 hashing algorithm, known for its vulnerability
to collision attacks where two different inputs can yield the same hash output, remain significant.
Git and platforms like GitHub have taken steps to mitigate the known SHA-1 vulnerabilities, but the
rapid advancement of technology may make such attacks more feasible in the future. This poses a
risk, especially in scenarios where different commits could potentially have the same SHA-1 hash
but different content. In response, the Git community started transitioning to the more secure
SHA-256 hash function. However, a major challenge in this transition is that there is no
interoperability between SHA-1 and SHA-256 repositories yet. This lack of compatibility poses
significant difficulties, especially in maintaining backward compatibility with the vast number of
existing repositories that use SHA-1. Consequently, the transition to SHA-256 has faced delays and complexities.

### 1.3 History and credit

In late 2018, Open Law Library began developing TAF as a part of its
efforts to publish the laws and the Code of the District of Columbia in
alignment with the Uniform Electronic Legal Material Act ([UELMA](https://www.uniformlaws.org/committees/community-home?CommunityKey=02061119-7070-4806-8841-d36afc18ff21)). Created by
the Uniform Law Commission, UELMA provides a structured approach for
governments to authenticate and preserve electronic legal materials. The
District of Columbia adopted its version of UELMA in 2017.

This project was made possible in part by the Institute of Museum and Library
Services [(LG-246285-OLS-20)](https://www.imls.gov/grants/awarded/lg-246285-ols-20) and
the [National Science Foundation (NSF)](https://www.nsf.gov).

### 1.4 Goals

In today's digital landscape, where important data is stored in Git repositories, TAF's purpose is
to add an extra layer of security beyond what Git and hosting platforms provide. TAF is focused on
authenticating and securely updating Git repositories. Moreover, TAF offers tooling for repository
management, such as: repository validation, cloning and updating repositories in place.

#### 1.4.1 Attack detection goals

TAF's principal goals encompass the detection of unauthorized pushes to Git repositories under its
protection, as well as any alterations to previously validated history. This could include the removal
or substitution of commits. Validation should not rely on information stored on code hosting
platforms like GitHub or GitLab (e.g., collaborator status or associated SSH and GPG keys), as an
attacker could potentially access a user's account or personal computer. It should be impossible to
make changes to the Git repositories without signing TUF metadata files, preferably using a threshold
of hardware keys, in a way that passes TAF's validation.

#### 1.4.2 Redundancy

Interested parties should be able to securely and easily create local copies of the protected Git
repositories (provided they are publicly accessible), along with the corresponding TUF data for
validation, even if they do not have update privileges. They should be able to validate all signatures
and attestations, extending back to the repository's first commit. Additionally, they should have
the means to directly verify the integrity of the initial commit by reaching out to the official
repository maintainers via alternative channels, such as a telephone call.

This approach lays the foundation for designing systems where multiple participants can download and
host repositories, serving as an additional layer of security. The existence of backup copies can aid in
recovery from attacks, including those exploiting SHA-1 vulnerabilities. However, it's important to note
that such a system, while buildable on top of TAF, extends beyond TAF's core functionalities. The
detailed exploration of this extended application is covered in a separate document.

#### 1.4.3 User experience goals

User experience goals include:

- Ease of setup and maintenance: providing tools and utilities designed to simplify the initial
configuration and all subsequent updates of TUF metadata files and TUF target files containing
information about relevant Git repositories. Additionally, ensuring ease of configuration and usage
of hardware keys for signing.
- Safe and simple update of Git repositories: ensuring that the processes for cloning and updating
repositories under TAF's protection are user-friendly and straightforward, offering clear and helpful
error messages to aid in troubleshooting any issues that arise.
- Content agnosticism: maintaining a design and functionality that is completely agnostic to the
content stored within the secured Git repositories. The framework should not make assumptions or
have expectations about the type of content it is protecting.

### 1.5 Non-goals

TAF does not aim to prevent unauthorized modifications of repositories.
Instead, TAF aims to detect such modifications. In the event of an attack, TAF seeks to
identify unauthorized changes and prevent them from being pulled down locally.

Moreover, TAF operates on top of Git and does not modify or enhance Git's underlying functionality or
security features. While Git has known vulnerabilities, such as susceptibility to collision attacks,
addressing these issues at the Git level is outside TAF's scope.

Content in TAF-secured repositories and their update methods are irrelevant. TAF's role activates
post-commit, validating and marking changes in these repositories as official.

## 2 System overview

TAF provides a method for validating and securely updating Git repositories, ensuring the
integrity of not just their most recent state, but their complete history as well.

At the core of the system is an authentication repository, which is a Git repository as well.
However, at any given revision, it also functions as a valid TUF repository, containing target
and metadata files. The authentication repository holds information about the Git repositories
it protects, most notably their commit histories, and refers to them as target repositories.
Being a TUF repository, the authentication repository incorporates key TUF concepts such as
roles, signing keys, metadata, and target files.

TAF utilizes the four fundamental roles defined by the TUF specification: `root`, `targets`,
`snapshot`, and `timestamp`. Additionally, TAF supports the use of delegated targets roles.
Similarly, the metadata file format in TAF is consistent with the standard established by TUF.
Detailed descriptions can be found in TUF specification:

- [Roles and PKI](https://github.com/theupdateframework/specification/blob/master/tuf-spec.md#roles-and-pki--roles-and-pki)
- [Metadata Format](https://github.com/theupdateframework/specification/blob/master/tuf-spec.md#metaformat--metaformat)

In TAF, target files preserve their original definition from TUF. On the other hand,
TUF allows flexibility in choosing filenames and directory structures for target files within a
repository, while TAF sets clear guidelines. It requires a specific directory structure, mandates target
files named after their respective target repositories, and requires additional target files that link
an authentication repository with its target repositories and other authentication repositories.
Furthermore, TAF supports the use of YubiKeys, although it does not make their use mandatory.

The following are high-level actors their corresponding actions within the framework:

- Maintainers: use tools provided by TAF to set up the authentication repository and provide
information about the target repositories.
- Maintainers: after new commits are pushed to the target repositories, use TAF tools to update
corresponding information stored in the authentication repository.
- Users: use a tool provided by TAF, known as the "updater", to validate remote repositories and
synchronize their local copies of the repositories with the remote:
  - validate the authentication repository by ensuring that, at each commit, the repository's
  state complies with TUF's specifications.
  - perform validation of target repositories based on the data stored in the authentication
  repository. Compare commit SHAs stored in the authentication repository with actual commit
  SHAs of the target repositories.
  - create or update local copies of the authentication and target repositories as necessary.

One important thing to note is that, since the authentication repository is also a Git
repository, there's no need to store the entire commit history of target repositories all at
once. Instead, each commit in the authentication repository represents a specific valid state
of the whole set of target repositories. To access previous valid states, refer to older
commits within the authentication repository.

### 2.1 Content addressable systems and TUF

Content addressed systems such as Git have artifact integrity capabilities which can be
complemented by all of TUF's other features. The current TUF specification requires
targets to be files.

[TUF Augmentation Proposal (TAP) 19](https://github.com/theupdateframework/taps/blob/master/tap19.md), which is still in draft form, states that if some
artifacts—whether TUF metadata or otherwise—were stored in a content-addressed system, they
would each already be associated with a unique identifier created by that system using the
content of the artifact. This TAP updates the definition of a target identifier from being
solely a path relative to a repository and also allows URIs to point to different resources.

With the adoption of TAP 19, storing commit SHAs in separate target files will no longer be
necessary. However, TAF will still need to ensure backward compatibility with older
authentication repositories.

## 3 Authentication repository

As already stated, the authentication repository is a Git repository which, at every revision,
is a valid TUF repository. It contains metadata and target files, which adhere to TUF's
specification. Additionally, as a Git repository, it tracks changes of these files over time.
An authentication repository stores information about target repositories and, optionally,
about other authentication repositories. The structure of certain target files is strictly
defined, which is where an authentication repository and a generic TUF repository diverge.

### 3.1 Repository layout

Like all TUF repositories, the filesystem layout of an authentication repository includes metadata and
targets directories. The TUF specification does not mandate a specific structure or name for the directory
that stores the target files. Nevertheless, TAF adopts the naming convention from TUF's reference
implementation, which means that metadata files MUST be inside a directory called `metadata`, while the
target files MUST reside in a directory named `targets`.

Technically, an authentication repository does not have to reference any target
repositories, but if it does, a strict naming convention is enforced. This naming convention mimics that
of GitHub, where the names of the target repositories are structured in two parts:

- Organization name (referred to as namespace by TAF)
- Repository name

Organizations in GitHub are shared accounts where businesses, open-source projects, or other
collaborative groups can manage multiple repositories. Repositories host project files and
enable version control. So the `organization/repository` format is used for various
operations involving repositories in GitHub.

In TAF, a target repository MUST be identified by its full name, which consists of a namespace
and its name, formatted as `namespace/repository`. This full name MUST be unique within the
context of a single authentication repository.

The validation of target repositories in TAF is executed by comparing the commit SHAs listed in the
target files of the authentication repository against the actual commits present in these
repositories. The location and names of these target files within the `targets` directory MUST adhere
to a specific convention. Each file is named after its respective repository, and its parent directory
is named after the repository's namespace. For instance, if a repository's full name is
`namespace/repository`, the commit SHA will be stored in the `targets/namespace` folder, in a file
named `repository`.

Moreover, to specify the associations between an authentication repository and its
target repositories, as well as relationships between different authentication
repositories, TAF introduces specifically named and structured target files. Only
individuals in possession of the necessary targets keys can modify these files,
ensuring any unauthorized changes are identified and flagged. These target files include:

- `repositories.json`: This file provides a list of the target repositories.
- `dependencies.json`: This file contains details about other authentication repositories.
- `mirrors.json`: This file plays a role in determining the URLs used to download the repositories.
- `protected/info.json`: This file contains the authentication repository's metadata.
- `scripts` directory: Contains post-update hooks.

All types of target files will be described in more detail in the next section.

Note: TAF currently relies on and maintains a TUF fork on version [0.20.0](https://github.com/openlawlibrary/tuf). Our near term plan is to transition TAF to use the latest TUF. See [tracking issue](https://github.com/openlawlibrary/taf/issues/274) for more details. Once that transition is done, it might be possible to remove some of these files and move this information to metadata files.

### 3.2 Target files

TAF requires certain types of target files in order to perform validation of repositories.
Modifying these target files involves updating and signing TUF metadata files. This process ensures a high
level of security, as only individuals possessing the signing keys are authorized to make changes.
It is worth noting that TAF allows existence of additional target files, not included in this
overview, if a specific use-case requires them.

Note: if information from this section is moved to metadata files, the section will be updated. However,
maintaining backward compatibility will always be necessary.

#### 3.2.1 repositories.json

In TAF, an authentication repository is configured to reference one or more Git repositories, which
can contain various types of content. These are known as target repositories.
All target repositories MUST be listed in a specific target file named `repositories.json`.
As previously mentioned, TAF identifies repositories using a naming convention that combines
a namespace with the names of individual repositories within that namespace.

An example of this file is as follows:

```markdown
{
  "repositories": {
    "namespace/repo1": {
      "custom": {
        "custom_property": "custom_value"
      }
    },
    "namespace/repo2": {
      "custom": {
        "custom_property": "custom_value",
        "allow-unauthenticated-commits": true
      }
    }
  }
}
```

In this JSON structure:

- Each repository MUST be identified uniquely, like `namespace/repo1` and `namespace/repo2`
- Within each repository's configuration, there MAY be a `custom` property allowing for the
specification of additional data that might be useful to the repository's maintainers and is
not required by TAF.
  - One exceptions is the `unauthenticated-commits` custom property. When this
  property is set to `true` for a target repository, it indicates that the repository is permitted
  to contain unauthenticated commits between authenticated ones. This effectively means
  that a target repository can include commits that are not stored in the authentication
  repository. In such cases, TAF's updater tool is designed to recognize and skip over these
  unauthenticated commits during its validation process.

Note: this is how TAF works and this concept of unauthenticated commits is something that we need in order to improve user experience at the moment. It was inspired by how our biggest partner is using the platform and their preferred workflows. I know that we talked about it and that it might be problematic. Additionally, I'm realizing that it makes little sense to place a property that the framework uses under custom. This needs to be addressed, but we still need backwards compatibility.

#### 3.2.2 mirrors.json

This file is used for determining the URLs of repositories. It MUST be present in cases where the
authentication repository references other repositories, whether they are target repositories or
additional authentication repositories. It utilizes a dynamic resolution mechanism, which
is closely tied to the repository information specified in `repositories.json`. `mirrors.json`
contains URL templates with placeholders – `{org_name}` and `{repo_name}`. The actual URLs for
each repository are resolved by replacing these placeholders with the corresponding namespace and
name of the repository, as defined in `repositories.json`.

To illustrate the URL resolution process in TAF, let's consider an example where `mirrors.json`
is structured as follows:

```markdown
{
    "mirrors": [
        "http://github.com/{org_name}/{repo_name}",
        "http://github.com/{org_name}-backup/{repo_name}",
        "git@github.com:{org_name}/{repo_name}.git",
        "http://gitlab.com/{org_name}/{repo_name}"
    ]
}
```

For instance, if a repository is named namespace1/name1 in repositories.json, the corresponding
URLs generated by TAF will be:

- `http://github.com/namespace1/name1`
- `http://github.com/namespace1-backup/name1`
- `git@github.com:namespace1/name1.git`
- `http://gitlab.com/namespace1/name1`

In practice, when TAF attempts to clone or pull a repository, it follows a sequential approach
based on the URL list generated from `mirrors.json`. If the first attempt fails, perhaps due to
accessibility issues or server downtime, TAF then proceeds to the next URL in the list.

#### 3.2.3 commit data

In TAF, commit SHAs for each target repository are stored in a structured manner. The storage
location is determined by the namespace and name of the repository. For a repository named
`namespace1/name1`, the commit SHA data is stored in a directory named `namespace1`, in a file titled
`name1`. These files are in JSON format and MUST include the commit SHA and the branch name, and
MAY contain other custom properties. An example of this file's contents is:

```markdown
{
    "branch": "publication/2023-02-08",
    "commit": "e8fb452333c81a42cd3297b33a9875d57588052b",
    "custom_property": "custom_value"
}
```

The system is designed to store only the current commit SHA for each target repository and its branches
at any given time. As the authentication repository itself is a Git repository, every commit in it
represents a valid snapshot of the target repositories. When there's a change in the target
commit SHA, the respective file in the authentication repository is updated along with the
metadata files. These updates are then signed and committed. Further details on this process will
be provided in a subsequent section.

#### 3.2.4 dependencies.json

This file allows definition of hierarchies of authentication repositories. This allows the
designation of a primary, or root, authentication repository, which can be linked to one or more
secondary authentication repositories. TAF's updater can automatically pull the entire
hierarchy of linked repositories.

One important concept introduced in this file is out-of-band authentication. Before an
authentication repository is referenced, an additional layer of verification SHOULD be performed.
This involves direct, external validation, typically through communication with the repository's
maintainer. The purpose of this step is to ascertain that the repository in question is indeed
the official one and not a fraudulent version created by an attacker. During this out-of-band
communication, maintainers are expected to provide a commit SHA (typically of the first commit),
which serves as a proof of authenticity. This commit SHA can then be recorded in `dependencies.json`
file. When the updater tool processes the repositories, it checks for the presence of this
recorded commit. If the repository’s actual commit SHA of the initial commit does not match the
one stored in `dependencies.json`, the updater raises an error, signaling a potential security
issue. Although detailed discussions on building a web of trust are reserved for a
different document, it's important to note that this out-of-band data can lay the groundwork for
such a system.

This is an example of a `dependecies.json`:

```markdown
{
    "dependencies": {
        "namespace1/auth_repo": {
            "out-of-band-authentication": "bfcbc7db7adc3f43291a64b0572b6b114e63e98a"
        },
        "namespace2/auth_repo": {
            "out-of-band-authentication": "d7a6b796cffe53ad89b4504084402570b7d17f6b"
        }
    }
}
```

In this configuration each entry under the dependencies key represents a separate authentication
repository, identified by its namespace and name. A referenced repository's full name, with namespace,
MUST be unique within one authentication repository.

#### 3.2.5 protected/info.json

The `protected/info.json` file in TAF is a supplementary file that is meant for
storing authentication repository's own metadata, or, more specifically, its name.
An example of the file's content is as follows:

```markdown
{
  "namespace": "some_org_name",
  "name":  "some_repo_name"
}
```

This file contains the namespace and name of a repository. These fields together represent the
repository in the `namespace/name` format within TAF. In cases where `protected/info.json` does
not exist, TAF's updater tool will attempt to infer the repository's namespace and name from
its filesystem path.

#### 3.2.6 Scripts

Every authentication repository MAY contain target files inside `targets/scripts` folder which
are expected to be Python scripts which will be executed after successful/failed update of
that repository. More detailed information about the purpose and functionality of these
scripts will be covered in later, when describing the updater.

### 3.3 Creation and update of authentication repositories

Initializing an authentication repository in TAF involves the following steps:

- Creation of the initial TUF repository: this includes generating initial metadata files that conform to
the TUF specification. To do so, it is necessary to specify customizable properties of TUF repositories,
such as:
  - Keys that will be responsible for signing specific metadata files, in other words, assigning keys to
  various roles as defined in the TUF specification.
  - Signature thresholds per roles.
  - Delegated roles and their properties. These roles allow for more detailed control over target files.
  For each delegated role, the paths they are trusted to provide are specified.
- Handling existing target files: if the `targets` folder already exists on disk, at the intended location,
and contains target files, these files should be included in the initial version of the repository's
`targets` metadata file, or those of a delegated role.
- Initialization of a new Git repository: set up a new Git repository and a default branch, typically
named `main`. This step may also involve setting up a remote.
- Committing initial metadata and target files: the final step is to commit the initial metadata and
target files to the repository, marking the start of its version history.

Updating metadata and target files in TAF is done in accordance with the TUF specification.
However, after each update, changes are committed. An update does not simply mean modification
of any metadata or target file, but a valid update of the TUF repository as a whole. Therefore:

- If any metadata file is updated, it needs to be signed by at least the threshold of keys.
- If the snapshot is updated and signed, the `timestamp`(which stores the hash, length,
 and version of the `snapshot` file) is also updated and signed.
- If the `root` or a `targets` role is updated, `snapshot`, which stores versions
of these files, is updated as well.
- If a target file is updated, information about it in the appropriate targets metadata
file (`targets` or one corresponding to a delegated role) is updated and signed too.

This all ensures that each revision of the authentication repository constitutes a valid TUF repository.
Additionally, the version numbers of metadata files in revisions corresponding to subsequent commits
should either remain the same or differ by one. In essence, this means that only one valid update of the
TUF repository is permitted per commit. Consequently, all updates to the repository are transparent, and
all previous versions remain accessible.

Here's an example of how an initial repository might be structured in TAF, with the first set of versioned
metadata files:

```markdown
Commit SHA: 1234abcd

- metadata/
  │
  ├─ root.json (v1)
  ├─ targets.json (v1)
  ├─ snapshot.json (v1)
  └─ timestamp.json (v1)
- targets/
```

Now let's say that `repository.json` is added:

```markdown
Commit SHA: 5678efgh

- metadata/
  │
  ├─ root.json (v1)
  ├─ targets.json (v2)
  ├─ snapshot.json (v2)
  └─ timestamp.json (v2)
- targets/
  │
  └─ repository.json
```

Finally, let's assume that a new signing key had to be added, which means that `root.json` had
to be modified and signed:

```markdown
Commit SHA: 5678efgh

- metadata/
  │
  ├─ root.json (v2)
  ├─ targets.json (v2)
  ├─ snapshot.json (v3)
  └─ timestamp.json (v3)
- targets/
  │
  └─ repository.json
```

To ensure ease of use in managing and maintaining authentication repositories, TAF is equipped with a
series of Command Line Interface (CLI) commands. These commands are designed to automate the setup
process, making it accessible and efficient for users. By simply inputting parameters for signing
keys, signature thresholds, and roles, the CLI commands facilitate the automatic creation of
authentication repositories. Additionally, for the purpose of updating repositories, TAF's CLI
commands are tailored to simplify the modification of target and metadata files. This includes tasks
such as updating the expiration dates of metadata files. The commands also enable the addition of new
roles, the integration of new target and reference authentication repositories within the TAF
framework.

## 4 Tracking valid states of target repositories

This section explains how TAF tracks changes across multiple target repositories.
TAF treats all target repositories as parts of a single, integrated system. The authentication
repository is key in this process, as it records the combined state of all target repositories at
any given time. By examining the commit history of the authentication repository, we can
view and understand the evolving state of this system of repositories over time.

As previously mentioned, target repositories are specified in `repositories.json`, and through
the combined information stored in this file along with `mirrors.json`, their URLs are defined.
The updater uses this information in order to initially clone these repositories. The specifics of
this cloning process will be discussed in greater detail in a later section.

Now, let's consider an example where we have three target repositories: `namespace1/repo1`,
`namespace1/repo2`, and `namespace1/repo3` and freshly initialized authentication
repository containing TUF metadata files and initial target files (for simplicity, let's assume
that there are only the two necessary files, `repositories.json` and `mirrors.json` and that there
are no references to other authentication repositories):

```markdown
- metadata/
  ├─ root.json
  ├─ targets.json
  ├─ snapshot.json
  └─ timestamp.json
- targets/
  ├─ repositories.json
  └─ mirrors.json
```

The three target repositories are initialized and each contain one commit (on branch `main`):

```markdown
namespace1/
│
├── repo1/
│   └── main: a1b2c3d4
│
├── repo2/
│   └── main: e5f6g7h8
│
└── repo3/
    └── main: i9j0k1l2
```

In order to register these commits as valid, their values need to be written to target files named
after the repositories (and according to TUF specification, `targets`, `snapshot` and `timestamp`
metadata files need to be updated too). So the next revision of authentication repository should
be:

```markdown
- metadata/
  ├─ root.json
  ├─ targets.json
  ├─ snapshot.json
  └─ timestamp.json
- targets/
  ├─ repositories.json
  └─ mirrors.json
  └─ namespace1/
      ├─ repo1
      │   └─ {"branch": "main", "commit": "a1b2c3d4"}
      ├─ repo2
      │   └─ {"branch": "main", "commit": "e5f6g7h8"}
      └─ repo3
          └─ {"branch": "main", "commit": "i9j0k1l2"}
```

This means that after target and metadata files are updated, the authentication repository's
changes need to be committed.

Now, consider a scenario where a user updates `repo1` and commits these changes. If `repo1` is
allowed to contain unauthenticated commits, according to `repositories.json`, there are two
possibilities:

- The change can be recorded in the authentication repository. In this case, the updater tool is
designed to raise an error if this commit is not detected when cloning or updating `repo1`.
- Alternatively, this commit can be omitted from being recorded in the authentication repository,
in which case the updater will not look for it while traversing through commits of `repo1`.

However, for repositories that are not permitted to contain unauthenticated commits, any new
commit must be registered in the authentication repository. For instance, in the case of `repo1`,
if it's not allowed to have unauthenticated commits, then its corresponding target file,
`namespace1/repo1`, must be updated in the authentication repository to include the new commit.
If the new commit in `repo1` is, for example, `e3f4g5h6`, then the next revision of the
authentication repository will reflect this update:

```markdown
- metadata/
  ├─ root.json
  ├─ targets.json
  ├─ snapshot.json
  └─ timestamp.json
- targets/
  ├─ repositories.json
  └─ mirrors.json
  └─ namespace1/
      ├─ repo1
      │   └─ {"branch": "main", "commit": "e3f4g5h6"}
      ├─ repo2
      │   └─ {"branch": "main", "commit": "e5f6g7h8"}
      └─ repo3
          └─ {"branch": "main", "commit": "i9j0k1l2"}
```

Next, let's say that `branch1` is created in repositories `repo2` and `repo3` and one commit is
created in each repository. Let's say that the two repositories are updated at the same time
(meaning that if something is committed to `branch1` of `repo2`, something has to be committed to
`branch1` of `repo3` as well). The current state of these target repositories would now look like
this:

```markdown
namespace1/
│
├── repo1/
│   └── main: a1b2c3d4, e3f4g5h6
│
├── repo2/
│   ├── main: e5f6g7h8
│   └── branch1: i7j8k9l0
│
└── repo3/
    ├── main: i9j0k1l2
    └── branch1: m2n3o4p5
```

The next revision of the authentication repository is then:

```markdown
- metadata/
  ├─ root.json
  ├─ targets.json
  ├─ snapshot.json
  └─ timestamp.json
- targets/
  ├─ repositories.json
  └─ mirrors.json
  └─ namespace1/
      ├─ repo1
      │   └─ {"branch": "main", "commit": "e3f4g5h6"}
      ├─ repo2
      │   └─ {"branch": "branch1", "commit": "e5f6g7h8"}
      └─ repo3
          └─ {"branch": "branch1", "commit": "m2n3o4p5"}
```

By navigating through the commit history of the authentication repository, it's possible to
collect all registered commits for each target repository and each of their branches. So, within
the TAF framework, there's no need to track all past commits of target repositories in a single
revision of the authentication repository. Similarly, previous versions of metadata files can be
easily accessed through the Git history.

## 5 Updater

This section focuses on the Updater, a key component of the TAF framework. The Updater's main job is
to securely clone and update both authentication and target repositories. It replaces the need for
manually running Git commands with its automated process. This is especially important because it
incorporates a validation step, ensuring that all changes are verified before being applied to the
user's machine.

As previously discussed, one authentication repository in TAF can reference another. This
functionality is particularly useful for scenarios where an organization needs to create local
copies of repositories managed by another organization. Currently, this inter-repository linkage is
defined using the `dependencies.json` file. Before exploring this use-case in more detail, we will
first examine the update process for an authentication repository that does not have any such
dependencies

### 5.1 The update process

The update process in TAF begins with specific inputs: the file system location of the authentication
repository, the URL of the remote repository if a local copy does not exist, and optionally, an
out-of-band commit. The out-of-band commit, which for now is expected to be first commit of the
authentication repository, is obtained by contacting the official publishers of the repository. If
this commit is provided, it acts as a verification step to ensure there's no mismatch between the
expected initial commit and the actual first commit in the remote repository. This verification
helps to detect scenarios where users might be directed to download a repository from untrustworthy
sources, such as those created by malicious actors.

The update process in TAF can be broken down into the following steps:

1. Clone the authentication repository as a bare Git repository to a temporary location. Validate its
compliance with TUF specification at every revision, starting from the previously saved last
validated commit. Check the out-of-band commit if provided.
1. Update the user's existing local repository copy or create a new one if it doesn't exist.
1. Clone target repositories if they are not present locally, or fetch their changes. Do not merge new changes.
1. Compare the data in the authentication repository with the fetched commits of target repositories.
1. Execute any scripts designated to run after the update process

After each successful update, TAF stores the last validated commit of the authentication repository
in a file on the user's local machine. This file is placed in a folder named with the authentication
repository's name, prefixed with an underscore (_). The purpose of saving this commit is to optimize
future updates by avoiding starting from the first commit each time.

Note: At the moment, there are no implemented security measures which would make it harder to
manually modify the file storing this last validated commit. That should be addressed in the future.
We have not yet thoroughly thought about what would be the best way to do that.

#### 5.1.1 Validate the authentication repository

The update process begins with cloning the authentication repository to a temporary location as a
bare Git repository. If a URL is provided when calling the updater, the repository is cloned from
that location. If no URL is provided but a user's local repository already exists, the URL is
determined based on its remote. In a bare Git repository setup:

- There is no work tree or checked out copy of the source files.
- Git's revision history is stored directly in the root folder of the repository, as opposed to being
within a `.git` subfolder, which is typical in non-bare repositories.
- After the cloning process is complete, no checkout of the `HEAD` is performed. This is equivalent
to applying the `-n` option in the `git clone` command, which skips the checkout step and leaves the
working directory empty.
- if there are malicious files in the repository, they are not directly written to disk in a form that
could be inadvertently executed or opened.

Once the repository is cloned, the updater tries loading the last validated commit. If this commit is
not found, the update process starts from the repository's first commit. If the last
validated commit does exist, the updater checks if it is present in the newly cloned authentication
repository. If not found, an error is raised, suggesting possible forced removal of commits from the remote repository
or manual tampering with the last validated commit information.

During the update process, the TAF updater iterates through the commits of the bare repository, starting
from the first commit identified for validation. It checks the transition from each commit `c1` to the
subsequent commit `c2`, ensuring the TUF repository at `c1` can update to the state at `c2`. This
procedure mostly aligns with the [client workflow in TUF specifications](https://github.com/theupdateframework/specification/blob/master/tuf-spec.md#update-the-timestamp-role--update-timestamp),
with these specific adaptations in TAF:

- In TAF, for a metadata file at version `n` in commit `c1`, the version in commit `c2` must be `n` or
`n + 1`. This rule ensures no intermediate versions are missed, differing from TUF where updating from
`n` to `m` is permissible as long as `n < m`.
- Due to its archival purpose, TAF requires validation of older metadata and target files, even after
their expiration dates. This means that the validation process in TAF does not fail because a metadata
file's expiration date has passed.


#### 5.1.2 Validate target repositories

Once the authentication repository has been validated, the next step is to validate the target
repositories, relying on the information about them stored in the authentication repository.
A challenging aspect of validating target repositories is their potential variety of states, since users
can perform various actions on their local copies (like manually pulling or creating new commits without
pushing). The updater must be robust enough to handle all these situations. The update should not always
fail if the user manually pulled valid commits, or if they committed something on top of the last remote
commit. However, the next overview will focus on the general idea, not delving into these specific
details. Here are the steps involved in this validation process:

- As mentioned earlier, authentication repositories record valid commits of target repositories in
target files named after these repositories. The first step is to extract lists of commits per branch
for each target repository. These target files are JSON files containing data in this format:

```markdown
{
  "branch": "main",
  "commit": "e3f4g5h6"
}
```

- Fetch new commits (without pulling, which includes merging) or clone target repositories without
checking out files for additional safety. This step avoids merging changes into local branches and
prevents immediate exposure to the files in the repository. The URLs of the target repositories are
determined based on the `repositories.json` and `mirrors.json` files, as explained earlier.
- Compare commits extracted from the authentication repository with the fetched ones in a breadth-first
manner. This involves checking each target repository against the target files contained in a given
authentication repository's commit, then moving to the next commit. The process stops if there is a
mismatch.
- If a repository is allowed to contain unauthenticated commits, an error is not reported as long as
all commits listed in the authentication repository are found in that target repository in the correct
order, even if there are additional unlisted commits.
- After the validation process is completed, whether it ends successfully or with an error, the next
action is to merge the last successfully validated commit into each respective repository.

After successfully validating the target repositories, the final step is to merge the last validated
authentication commit into the local copy of the authentication repository. Once this is done,
record this commit SHA in the `last_validated_commit` file. This action ensures that the local
authentication repository is up-to-date with the latest validated state and that this state
is accurately recorded for future reference.

An important aspect of TAF's update process is the determination of destination paths for target
repositories on the filesystem. When initiating the updater, an optional input parameter can be
provided that specifies the root location for all repositories. For instance, if this root location
is set to /dir1/dir2, the path for a target repository will be formed by appending its full name to
this path. This would result in a path like /dir1/dir2/namespace/name1 for the target repository.

In cases where this root path is not explicitly provided, TAF defaults to determining it based on the
path of the authentication repository. It assumes that the full name of the authentication repository
is included in its path, and the root for the target repositories is located two directories up from
the authentication repository's location."

Suppose the path of the authentication repository is `/dir1/dir2/namespace/auth_repo`.
Considering that the authentication repository's full name (`namespace/auth_repo`) is included
in its path, TAF calculates the root location for target repositories as `/dir1/dir2`.

#### 5.1.3 Execute handlers

TAF incorporates the functionality to execute custom scripts after the updater has run,
providing flexibility to respond to various outcomes of the update process. To be more precise,
TAF recognizes the following events:

- Succeeded: This event indicates that the updater ran without any issues.
- Changed: This signifies that the update was successful and detected changes.
- Unchanged: This means the update was successful, but no changes were detected.
- Failed: This event is triggered if an error occurred while running the updater.
- Completed: Similar to a 'finally' block in programming, this event occurs regardless of the update's
success or failure.

For instance, if an update is successful and changes are detected, TAF will trigger the `changed`,
`succeeded`, and `completed` events in sequence.

In TAF, scripts are associated with specific events by being placed in designated folders within the
targets/scripts directory of the authentication repository. This means that all script files are also
TUF target files, and any modifications to them require signing the targets metadata. Each folder
within this directory is named after the event it corresponds to and can contain multiple scripts.
These scripts are executed in alphabetical order when their associated event is triggered. Below is an
outline of the structure for the scripts folder:

```markdown
/scripts
    /repo
      /succeeded - every time a repo is successfully pulled
      /changed
      /unchanged
      /failed - every time a repo is not successfully pulled
      /completed  - like finally (called in both cases)
    /update
      /succeeded - once after all authentication's repositories have been successfully pulled
      /changed
      /unchanged
      /failed - if one repository failed
      /completed  - like finally (called in both cases)
```

In TAF's `targets/scripts` directory, there are `update` and `repo` folders that correspond to
two levels of event triggers. The `repo` folder contains scripts triggered after updating a
single authentication repository. In contrast, the `update` folder contains scripts that are
executed once the entire update process for all repositories is complete.

In situations where a TAF authentication repository references other authentication
repositories, scripts in the repo folder will be executed multiple times. This execution occurs
for each update of the referenced authentication repositories, as well as for the top-level
authentication repository itself. On the other hand, scripts in the update folder are triggered
only once, at the very end of the entire update process.

In TAF, each script is expected to output JSON containing two types of data: persistent and
transient. The persistent data is automatically saved to a file named `persistent.json` after
every script execution. This file is then passed on to subsequent scripts. On the other hand,
transient data, while also passed to the next script, is not stored permanently.
In addition to handling persistent and transient data, these scripts also receive detailed
information about the repositories involved — this includes both the authentication repository
and its target repositories.

### 5.1.4 Updating repositories with cross-references

Within TAF, an authentication repository has the capability to reference other authentication
repositories. This relationship is defined in the `dependencies.json` file. Alongside the name of
each referenced repository, the file can also specify out-of-band commits. The URLs for these
referenced authentication repositories are determined similarly to target repositories. This involves
combining their full names in a `namespace/name`format with URL templates specified in `mirrors.
json`.

Once the primary authentication repository (including its own contents and targets) has been
validated without errors, the updater processes each repository listed in the `dependencies.json`. It
determines their URLs and then recursively updates each referenced authentication repository. When an
out-of-band commit is specified for a referenced repository, it is included in the update function.
The updater then conducts a validation check based on this commit, as described earlier.

## 6 Future directions and open questions

- If TUF's TAP 19 is approved and implemented, it will enable significant changes in how branch and commit
 information is stored. Specifically, it will allow the removal of target files that currently store branch
 and commit data, integrating this information directly into the targets metadata.
- A practical improvement involves storing aliases for signing keys in the metadata files. This feature
would enable linking a key ID to the owner's name, simplifying key management. Technically, this requires
transitioning to the Metadata API, moving away from TUF's older reference implementation. This is not a
problem, just requires dedicating some time to this.
- Another significant enhancement is implementing remote signing capabilities. This would allow individuals
in different locations worldwide to sign metadata files independently, with TAF then aggregating these
signatures.
- ...

Extensions built on top of TAF, aimed at addressing use-case-specific problems, will be detailed in separate
documents.
