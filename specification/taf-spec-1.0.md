# TAF specification 1.0

**Status:** draft. Items marked **Open** are not decided yet.

Version 1.0 changes how an authentication repository records the commits of its target
repositories. Everything else in the [TAF specification](taf-spec.md) still applies: TUF metadata,
`repositories.json`, `mirrors.json`, `dependencies.json`, `protected/info.json` and scripts.
The earlier layout, one target file per repository that names a branch and a commit, is called the
*legacy layout* in this document.

What changed from the legacy layout, and why, is in
[changes and security considerations](taf-spec-1.0-changes.md).

The key words MUST, MUST NOT, SHOULD and MAY are to be read as described in RFC 2119.

## 1 Terms

| Term | Meaning |
| --- | --- |
| Auth repo | An authentication repository |
| Data repo | A target repository listed in the auth repo |
| Auth commit | A commit on the auth repo's default branch. Readers validate auth commits in first-parent order |
| Ref | A git ref of a data repo, written `refs/heads/<name>` |
| Ref file | A target file in the auth repo that records the signed state of one ref |
| Entry | One data repo commit listed in a ref file |
| Signed position | The commit a ref is at according to its ref file |
| Clock | The time a reader validates at. Readers MUST accept it as an input, so that a library can be validated as of a past time |
| Finding | The result of a failed check: the check id, the data repo, the ref, the auth commit and a message. A finding is an error or a warning |

## 2 Spec version

`protected/info.json` declares the version of this specification the auth repo follows:

```json
{
  "namespace": "example",
  "name": "auth",
  "taf-spec-version": "1.0"
}
```

- The value is a string `MAJOR.MINOR`. An auth commit whose `info.json` has no `taf-spec-version`
  uses the legacy layout.
- A reader MUST refuse an auth commit that declares a major version it does not implement.
- The version MUST NOT go down from one auth commit to the next.
- A reader that implements only the legacy layout MUST refuse any auth commit that declares a
  version. Without that, it would find no legacy target files, authenticate no data repo, and
  report success.
- The auth commit that first declares 1.0 is the *migration commit* ([section 7](#7-migration-from-the-legacy-layout)).

## 3 Ref files

### 3.1 Paths

Each authenticated ref of a data repo has one ref file:

```text
targets/<namespace>/<repo>/refs/heads/<name>.json
```

- The path maps to exactly one git ref: `targets/example/site/refs/heads/builds/1.json` is the
  ref `refs/heads/builds/1` of the data repo `example/site`. `<name>` may have several segments.
  Each segment starts with a letter, a digit or `_`, holds only letters, digits, `.`, `_` and `-`,
  and doesn't end in `.lock`.
- Two names are reserved. `refs/heads/current.json` is the repo's current pointer, and any file
  whose name ends in `.moves.json` is a moves file. Neither stands for a git ref of that name.
- The data repos are the repos listed in `repositories.json`, which also carries their custom data.
  Only a listed repo's files under `refs/heads/` are ref files.
- Ref names carry no meaning for taf and no order. Refs are ordered by the auth commit that adds
  their ref file.

### 3.2 Kinds

A ref file has one of five kinds. The kind is read from the file name and the content:

| Kind | Recognized by | Section |
| --- | --- | --- |
| Moves file | its name ends in `.moves.json` | [3.6](#36-pointers-and-moves) |
| Current pointer | its name is `current.json` | [3.7](#37-the-current-pointer) |
| List ref | the content is a JSON array | [3.4](#34-list-refs) |
| Pointer | the content is an object whose `type` is `"sym"` | [3.6](#36-pointers-and-moves) |
| Branch ref | any other JSON object | [3.5](#35-branch-refs) |

A ref file that doesn't parse as its kind fails `ref.schema`: it isn't UTF-8 JSON, an object has a
duplicate key, an array is empty, or a field is missing or has the wrong form. Pointers, current
pointers, moves files, their entries and `fork` have exactly the fields shown below. Entries of list
and branch refs may have more ([3.3](#33-entries)).

### 3.3 Entries

```json
{"commit": "4f1c…", "publish-date": "2026-01-05", "note": "kept as is"}
```

| Field | Required | Meaning |
| --- | --- | --- |
| `commit` | yes | The data repo commit, as a lowercase hex object id |
| `publish-date` | no | The first day, `YYYY-MM-DD` in UTC, on which a pointer may move onto this commit |

Other fields are kept as they are. taf only checks that they never change.

### 3.4 List refs

A list ref is a JSON array of entries, oldest first. The last entry is the signed position.

```json
[
  {"commit": "a1…", "publish-date": "2026-01-05"},
  {"commit": "a2…", "publish-date": "2026-01-20"}
]
```

### 3.5 Branch refs

A branch ref is an object with an `entries` array, oldest first, an optional `fork`, and any other
header fields:

```json
{
  "fork": {"from": "refs/heads/builds/1", "commit-from": "b1…", "parent-tip": "b2…"},
  "entries": [
    {"commit": "c1…", "publish-date": "2026-02-01"},
    {"commit": "c2…", "publish-date": "2026-03-01"}
  ]
}
```

| Field | Meaning |
| --- | --- |
| `entries` | The branch's commits. At least one. The last is the signed position |
| `fork.from` | The ref this branch was started from. Present only when the branch forked |
| `fork.commit-from` | An entry of `from`. It is the first parent of this branch's first entry |
| `fork.parent-tip` | The last entry of `from` when this branch's ref file was added |

Header fields other than `entries` and `fork` are kept as they are. taf only checks that they never
change.

### 3.6 Pointers and moves

A pointer names a line of commits across branch refs. Its moves file records where on that line
the pointer has been.

`release/1.json`:

```json
{
  "type": "sym",
  "entries": [
    {"target": "refs/heads/builds/1", "commit": "b1…"},
    {"target": "refs/heads/builds/2", "commit": "c1…"},
    {"frozen-at": "c2…"}
  ]
}
```

`release/1.moves.json`:

```json
{
  "moves": [
    {"commit": "b1…", "moved-at": "2026-01-05T06:00:00Z"},
    {"commit": "c1…", "moved-at": "2026-02-01T06:00:00Z"},
    {"commit": "c2…", "moved-at": "2026-03-01T06:00:00Z"}
  ]
}
```

- Each target entry names a ref and the entry of it the pointer starts following. The first entry
  creates the pointer, and each later one re-targets it.
- The pointer's *line* is, for each target entry in order, the target's entries from its start
  commit on. A commit's position on the line is the last target entry whose part of the line holds
  it, and its index in that target.
- `frozen-at`, if present, is the last entry. It names the last move. Nothing is added to the
  pointer or its moves file after it.
- The moves file is `<name>.moves.json` next to the pointer `<name>.json`. Each move names a commit
  on the line and when the pointer moved there, written `YYYY-MM-DDTHH:MM:SSZ` in UTC. The last move
  is the pointer's signed position. A moves file whose pointer doesn't exist fails `ref.schema`.

### 3.7 The current pointer

`current.json` has the pointer format, without `frozen-at`. Its targets are pointers of the same
data repo:

```json
{
  "type": "sym",
  "entries": [
    {"target": "refs/heads/release/1", "commit": "b1…"},
    {"target": "refs/heads/release/2", "commit": "d3…"}
  ]
}
```

- Each entry switches to a pointer added after the previous target. Its `commit` is that pointer's
  first move.
- The repo's *current position* is the last move of the last target. The data repo's `main` ref
  shows it.
- A data repo with `current.json` MUST NOT also have a ref file for `main`.

**Open:** whether the ref that shows the current position is always `main`, or named in
`current.json`.

## 4 Roles

Delegated roles own ref files through path patterns. A `*` matches exactly one path segment, so a
role that owns every ref of a repo lists one pattern per depth of name in use:

```json
"paths": [
  "example/site/refs/heads/*",
  "example/site/refs/heads/*/*"
]
```

A ref file SHOULD be signed by the delegated role whose paths cover it. One signed by the
top-level `targets` role fails `ref.owner`, as a warning: TUF already stops a role from signing a
path it isn't delegated, so this only catches a mistake in the patterns.

## 5 Unauthenticated commits

A data repo MAY allow commits between its listed entries that no ref file names. The setting is
`allow-unauthenticated-commits` in the repo's `custom` object in `repositories.json`, and is false
when absent.

- It is read at each auth commit, from `repositories.json` at that commit. For auth commits before
  the migration commit, the value is the legacy one: `repositories.json` custom data updated with
  the `custom` object of the repo's legacy target file.
- While it is false, every commit of a ref is listed: each entry's first parent is the previous
  entry, and a first entry without a `fork` is a root commit (`ref.follows`).
- While it is true, an entry only has to be a first-parent descendant of the previous entry, a
  first entry may have parents that no entry lists (`ref.follows`), and a git ref ahead of its
  signed position is a warning (`gitref.branch`).
- From the migration commit on, it may go from true to false and never back.
- Entries listed while it was true are not checked again after it turns false.

## 6 Git refs

Readers never trust a data repo's git refs. They compare each one with its signed position and
use the signed position:

| Ref | Signed position | Warning | Error |
| --- | --- | --- | --- |
| Branch or list ref | its last entry | behind, on the ref's entries | ahead or off. Ahead is a warning while unauthenticated commits are allowed |
| Pointer | its last move | behind, on its line | ahead or off the line |
| `main`, with `current.json` | the current position | behind, on the last target's line | anything else |

A missing git ref counts as off. Git refs are checked once, against the last auth commit validated.

## 7 Migration from the legacy layout

An auth repo moves to 1.0 in one auth commit, the migration commit. Nothing in a data repo's
history changes.

### 7.1 Conversion

The migration commit's ref files are the conversion of the legacy history: the legacy target files
of every auth commit from the first to the migration commit's parent, in first-parent order.

1. For each data repo and each auth commit, read the legacy target file
   `targets/<namespace>/<repo>`: a `branch`, a `commit` and other fields.
2. If the commit is already the last entry of that branch, nothing is added. Otherwise, append an
   entry for the commit to that branch, with every field except `branch` and `commit`. Converted
   entries have no `publish-date` unless the legacy file had one.
3. Each renamed branch (7.2) becomes a branch ref under its new name, with no `fork`, and a pointer
   under its old name that targets it from its first entry. Every other branch becomes a list ref
   under its own name.
4. In a repo with pointers, `current.json` targets them in the order their branches first appeared.
   Every pointer except the last is frozen.

**Open:** how the moves of converted pointers are dated: one move to the last commit, dated at the
migration, or one move per commit, dated from a field of the legacy entries.

### 7.2 Renames

The migration MAY move a branch's commits to a new name and keep the old name for a pointer to
them. The pointer is the record of the rename: a branch is renamed when the migration commit has a
pointer of its name, and its new name is the ref that pointer first targets. So any reader can repeat
the conversion from the migration commit alone.

### 7.3 The migration commit

The migration commit:

- adds the ref files of the conversion, and removes every legacy target file, since a file and a
  directory can't share a path;
- changes delegated paths from `<namespace>/<repo>` to patterns under `<namespace>/<repo>/refs/heads/`;
- adds `taf-spec-version` to `protected/info.json` ([2](#2-spec-version)).

Other target files are unchanged. A branch that was renamed needs its new git ref in the data repo,
at the same commit as the old one, before the migration commit is published.

## 8 Validation

A reader validates auth commits in first-parent order. At each one it runs TUF, then the checks
below against the previous auth commit. Auth commits before the migration commit are validated with
TUF only; at the migration commit, `spec.migration` compares the result with the conversion of
everything before it.

A reader MUST NOT accept an auth commit with an error. It MAY accept the auth commits before it.

There are 21 checks. Each has an id that readers report and tests refer to.

### 8.1 Metadata

| Id | Fails when | Level |
| --- | --- | --- |
| `spec.version` | The declared major version is unknown, or the version goes down ([2](#2-spec-version)) | error |
| `spec.migration` | The migration commit's ref files differ from the conversion of the legacy history before it, with the renames its pointers show ([7](#7-migration-from-the-legacy-layout)) | error |
| `metadata.signed` | TUF rejects the auth commit | error |
| `metadata.version` | A role's version goes down, or a role's metadata changes without a new version. Versions no longer have to go up by exactly one | error |
| `metadata.expiry` | The timestamp metadata of the last auth commit has expired at the clock. Readers MUST NOT turn this into a warning | error |

### 8.2 Ref files

| Id | Fails when | Level |
| --- | --- | --- |
| `ref.schema` | A ref file doesn't parse as its kind ([3](#3-ref-files)) | error |
| `ref.owner` | A ref file is signed by the top-level `targets` role ([4](#4-roles)) | warning |
| `ref.append-only` | An entry, a move or a header field changed or was removed, or a ref file's kind changed | error |
| `ref.no-disappear` | A ref file is removed, or a data repo has no git ref for a ref file of the last auth commit | error |
| `ref.follows` | An added entry's first parent isn't the previous entry, or a ref's first entry without a `fork` has a parent. While unauthenticated commits are allowed at that auth commit, the previous entry only has to be a first-parent ancestor, and a first entry may have parents. Also fails when `allow-unauthenticated-commits` goes from false to true ([5](#5-unauthenticated-commits)) | error |
| `ref.fork-listed` | `fork.commit-from` isn't an entry of `fork.from`, or isn't the first parent of the branch's first entry ([3.5](#35-branch-refs)) | error |
| `ref.fork-tip` | `fork.parent-tip` isn't the last entry of `fork.from` at the auth commit that adds the branch | error |
| `ref.dates` | A `publish-date` is before an earlier entry's `publish-date` in the same ref. Entries without one are skipped | error |

### 8.3 Pointers

| Id | Fails when | Level |
| --- | --- | --- |
| `pointer.frozen` | A pointer entry or a move is added after `frozen-at`, or `frozen-at` isn't the last move ([3.6](#36-pointers-and-moves)) | error |
| `pointer.targets` | A target names a ref with no ref file, or a start commit that isn't one of its entries. A target of `current.json` that isn't a pointer fails too | error |
| `moves.forward` | A move's commit isn't on the pointer's line, or its position isn't after the previous move's | error |
| `moves.not-early` | A move's `moved-at` is before the `publish-date` of its commit, compared as UTC dates, or is after the clock. A commit with no `publish-date` can be moved onto at any time | error |
| `moves.not-backdated` | A move's `moved-at` is before the previous move's, or before the auth commit that added its commit's entry was committed. Commit dates aren't signed, so this is a warning | warning |
| `current.forward` | A `current.json` entry targets a pointer that isn't newer than the previous target, or its `commit` isn't that pointer's first move ([3.7](#37-the-current-pointer)) | error |

### 8.4 Git refs

| Id | Fails when | Level |
| --- | --- | --- |
| `gitref.branch` | A branch or list ref's git ref is ahead of or off its signed position. Behind is a warning, and so is ahead while unauthenticated commits are allowed ([6](#6-git-refs)) | error |
| `gitref.pointer` | A pointer's git ref isn't at its last move, or `main` isn't at the current position. Behind is a warning | error |

## 9 Security considerations

- Readers MUST use the signed position of a ref, never its git ref ([6](#6-git-refs)).
- In a repo that doesn't allow unauthenticated commits, every commit of a ref is listed. In one
  that does, commits that no entry lists, including any before a ref's first entry, are not signed
  states even though a later entry's hash covers them.
- Readers check what a pointer may do, not why it was created or re-targeted. A holder of the key
  that signs pointers can switch `current.json` to a new pointer over any authenticated branch.
- Expiry is the only defense against a mirror that keeps serving an old state, which is why
  `metadata.expiry` is never a warning.
- Readers that implement only the legacy layout and predate [2](#2-spec-version) don't refuse a
  1.0 repository. Every reader of a repository has to be upgraded before its migration commit is
  published.

[Changes and security considerations](taf-spec-1.0-changes.md) covers each of these in detail.
