# TAF specification 1.0: changes and security considerations

**Status:** draft, informative. It goes with the [1.0 specification](taf-spec-1.0.md), which is the
normative text. Where the two differ, the specification wins.

This document is for reviewers and implementers. For each change from the legacy layout it says
what taf did before, what version 1.0 does, what that protects against or weakens, and what an
implementation must get right. It ends with the risks of moving existing repositories, the risks
the design accepts, and questions for review.

"Legacy" means the layout and behavior described in the [TAF specification](taf-spec.md) and
implemented by taf's updater before version 1.0.

## 1 Summary

| # | Change | Effect |
| --- | --- | --- |
| [2.1](#21-one-append-only-file-per-ref) | One append-only file per ref, instead of one overwritten file per repo | Stronger |
| [2.2](#22-several-commits-per-auth-commit) | An auth commit may list several new commits of a ref | Neutral |
| [2.3](#23-where-a-ref-starts) | A ref without a fork header is authenticated from its first entry, not from its root commit | **Weaker** |
| [2.4](#24-pointers-and-moves) | Pointers and signed moves are new signed objects | New surface |
| [2.5](#25-expired-metadata) | Expired metadata is always an error | Stronger |
| [2.6](#26-spec-version) | The spec version is declared and never goes down | Stronger, with a transition gap |
| [2.7](#27-the-migration-commit) | The migration commit must equal the conversion of the legacy history | New trust bridge |
| [2.8](#28-unauthenticated-commits) | Allowing unauthenticated commits is read per auth commit, and can only be turned off | Stronger |
| [2.9](#29-git-refs) | Every authenticated git ref is compared with its signed position | Stronger |
| [2.10](#210-landing-time) | When a ref landed comes from unsigned git dates | Known gap |
| [2.11](#211-ref-ownership) | A ref file signed by the top-level `targets` role is only a warning | Neutral |
| [2.12](#212-metadata-versions) | Metadata versions only have to go up | Neutral |

## 2 Changes

The attacker considered is the one TAF already assumes: they may control the servers that host the
auth repo and data repos, serve any git objects or refs, withhold updates, and hold some of the
keys that are kept online. They can't forge signatures of keys they don't hold.

### 2.1 One append-only file per ref

- **Legacy:** each data repo has one target file, `targets/<namespace>/<repo>`, naming one branch
  and one commit. Each update overwrites it. The record of earlier states is the auth repo's git
  history, and readers only check the branch the file names at each auth commit.
- **1.0:** each authenticated ref has its own file, which lists every commit of that ref and only
  grows (spec [3](taf-spec-1.0.md#3-ref-files)). `ref.append-only` and `ref.no-disappear` reject a
  changed or removed entry, a removed file, and a missing git ref.
- **Effect:** stronger. A commit that was signed can't later be dropped from the record, and a ref
  that stops being updated is still checked.
- **Implementations must:** compare each auth commit's ref files with the previous auth commit's,
  not only the latest state.

### 2.2 Several commits per auth commit

- **Legacy:** each auth commit moves a data repo at most one commit forward on its branch, unless
  the repo allows unauthenticated commits.
- **1.0:** one auth commit may add several entries to a ref (`ref.follows`).
- **Effect:** neutral. Each added entry is a signed commit, and each must have the previous entry
  as its first parent. Nothing between them is unlisted.

### 2.3 Where a ref starts

- **Legacy:** when a target file switches to another branch, the updater expects the listed commit
  to be that branch's first commit. Every commit from the root on is then listed by some auth
  commit, so every state of the branch was signed.
- **1.0:** a branch ref may start anywhere. A `fork` header records the ref and commit it started
  from (`ref.fork-listed`, `ref.fork-tip`). A ref without one, and every list ref, is authenticated
  from its first entry only.
- **Effect:** weaker for history before a ref's first entry. Those commits are fixed by the git
  hash chain of the first entry, but no signature says any of them was a valid state. A reader that
  checks out the signed position isn't affected. A reader that uses older commits of a ref, for
  example to show history, must treat commits before the first entry, or before a fork's
  `commit-from`, as unsigned.
- **Implementations must:** never present a commit as authenticated because it is an ancestor of
  an entry.

### 2.4 Pointers and moves

- **Legacy:** none. Which state is current is whatever the target file names.
- **1.0:** a pointer follows a line of commits across branch refs, and its moves file records each
  move with a time (spec [3.6](taf-spec-1.0.md#36-pointers-and-moves)). `current.json` names the
  current pointer (spec [3.7](taf-spec-1.0.md#37-the-current-pointer)).
- **What the checks guarantee** against a holder of the key that signs pointers:
  - a pointer only covers commits that a ref file lists (`pointer.targets`);
  - it never moves backwards or off its line (`moves.forward`);
  - it never moves onto a commit before that commit's `publish-date`, or to a time after the
    reader's clock (`moves.not-early`);
  - nothing is added after it is frozen (`pointer.frozen`);
  - `current.json` only switches to a newer pointer, at that pointer's first move (`current.forward`).
- **What they don't guarantee:** why a pointer was created or re-targeted. A holder of the pointer
  key can create a new pointer over any authenticated branch, including one with older content, and
  switch `current.json` to it. Readers accept it, because no reader check re-derives pointers from
  the branches' contents. The writer is expected to enforce that policy. See [4](#4-accepted-risks-and-open-items).
- **Implementations must:** use the signed position, never a git ref, and take the clock as an
  input so that a past state can be checked as of a past time.

### 2.5 Expired metadata

- **Legacy:** taf's updater logs expired metadata at the newest auth commit as a warning, unless
  it runs in strict mode.
- **1.0:** `metadata.expiry` is an error, and readers must not turn it into a warning.
- **Effect:** stronger against freeze attacks, where a mirror keeps serving an old, validly signed
  state. Expiry is the only defense against them. The cost is that a repository whose timestamp
  isn't refreshed in time becomes unusable until it is.

### 2.6 Spec version

- **Legacy:** none.
- **1.0:** `protected/info.json` declares `taf-spec-version`. It never goes down, and a reader
  refuses a major version it doesn't know (`spec.version`). A reader that only knows the legacy
  layout must refuse any declared version (spec [2](taf-spec-1.0.md#2-spec-version)).
- **Effect:** closes downgrade from 1.0 to legacy rules.
- **Gap:** readers released before this rule existed don't refuse. On a 1.0 repository they find no
  legacy target files, authenticate no data repo, and report success. That can't be fixed in those
  releases. See [3](#3-moving-an-existing-repository).

### 2.7 The migration commit

- **1.0:** an existing repository moves to 1.0 in one auth commit. Its ref files must equal the
  conversion of the legacy target files of every earlier auth commit (`spec.migration`, spec
  [7](taf-spec-1.0.md#7-migration-from-the-legacy-layout)). Auth commits before it are validated
  with TUF only.
- **Effect:** this is what lets a new reader trust the converted history without replaying legacy
  rules. Without it, a migration could add entries the legacy history never signed.
- **Implementations must:** run the conversion from the signed legacy files themselves, with the
  renames the migration commit's pointers show, and compare ref file by ref file.

### 2.8 Unauthenticated commits

- **Legacy:** a repo may allow commits between the ones listed. The setting is read at each auth
  commit and can be turned on and off.
- **1.0:** the same setting, read at each auth commit. From the migration commit on it can be
  turned off and never back on (`ref.follows`). Entries listed while it was on aren't checked again.
- **Effect:** stronger. Once a repo requires every commit to be listed, gaps can't be reopened.

### 2.9 Git refs

- **Legacy:** readers check the branch the target file names. Commits on it past the signed one are
  an error only when the updater runs with `--upstream`; by default they are left unmerged.
- **1.0:** the git ref of every ref file, every pointer, and `main` for a repo with `current.json`,
  is compared with its signed position (`gitref.branch`, `gitref.pointer`). Behind is a warning;
  ahead or off is an error.
- **Effect:** stronger. Readers always use the signed position, and a tampered ref is reported
  rather than ignored.

### 2.10 Landing time

- **1.0:** `moves.not-backdated` compares a move's time with when its commit's entry landed, which
  is the auth commit's git date. Git dates aren't signed, so this check is a warning.
- **Effect:** a known gap. A move can be dated earlier than its target landed without an error.

### 2.11 Ref ownership

- **1.0:** a ref file should be signed by the delegated role whose paths cover it. One signed by the
  top-level `targets` role fails `ref.owner`, as a warning.
- **Effect:** neutral. TUF already stops a role from signing a path it isn't delegated. The check
  only catches path patterns that don't cover a ref name, for example a name with more segments
  than any pattern.

### 2.12 Metadata versions

- **1.0:** a role's version must go up whenever its metadata changes, and never down
  (`metadata.version`). It no longer has to go up by exactly one.
- **Effect:** neutral. TUF already rejects a rollback. The rule lets independent updates to
  different roles land in any order.

## 3 Moving an existing repository

The specification can't protect readers that don't implement it. Before an existing repository's
migration commit is published, every reader of that repository must refuse spec versions it doesn't
know ([2.6](#26-spec-version)). That includes taf's updater, any tool that reads target files
through taf, and any program that reads `targets/<namespace>/<repo>` itself.

The order is:

1. Release taf readers that refuse a declared spec version they don't implement.
2. Upgrade every reader of the repository to such a release, or to one that implements 1.0.
3. Push the new git refs that renames need to the data repos.
4. Publish the migration commit.

Readers should run with expired metadata treated as an error ([2.5](#25-expired-metadata)). An
attacker who serves the last legacy auth commit indefinitely is otherwise only stopped by expiry.

A migration can be undone until it is published. After that it only goes forward, since the spec
version and role versions never go down.

## 4 Accepted risks and open items

| Item | Status |
| --- | --- |
| A key that signs pointers can switch `current.json` to a new pointer over any authenticated branch ([2.4](#24-pointers-and-moves)) | Accepted. Readers check the invariants above; the policy for when a pointer is created or re-targeted is the writer's |
| History before a ref's first entry is unsigned ([2.3](#23-where-a-ref-starts)) | Accepted. Forks make lineage explicit where it matters |
| Landing time is unsigned ([2.10](#210-landing-time)) | Open. A signed landing time would make `moves.not-backdated` an error |
| Released legacy readers report success on 1.0 repositories ([2.6](#26-spec-version)) | Accepted. Mitigated by the order in [3](#3-moving-an-existing-repository) |
| How the moves of converted pointers are dated | Open (spec [7.1](taf-spec-1.0.md#71-conversion)) |
| Git uses SHA-1 commit ids | Unchanged from legacy; see the TAF specification |

## 5 Questions for review

1. **Pre-migration history.** At the migration commit, is `ref.follows` run over every converted
   entry, with the unauthenticated-commits setting of the auth commit that listed it? If not, a new
   reader relies on `spec.migration` alone and never checks that converted entries follow each
   other.
2. **Pointer key compromise.** Is it acceptable that readers don't re-derive pointers
   ([2.4](#24-pointers-and-moves)), given that the pointer key is likely kept online?
3. **Fork-less refs.** Should a ref without a fork be required to start at a root commit, as
   legacy branches effectively did ([2.3](#23-where-a-ref-starts))?
4. **Strict expiry.** Is treating expiry as an error in every reader the right default, given the
   availability cost ([2.5](#25-expired-metadata))?
