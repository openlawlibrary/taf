# Branch's Commits Schema

```txt
repo_update.schema.json#/properties/update/properties/target_repos/patternProperties/^.*$/properties/commits/patternProperties/^.*$
```

Commit before pull, after pull and lists of new and unauthenticated commits belonging to the given branch

| Abstract            | Extensible | Status         | Identifiable | Custom Properties | Additional Properties | Access Restrictions | Defined In                                                                           |
| :------------------ | :--------- | :------------- | :----------- | :---------------- | :-------------------- | :------------------ | :----------------------------------------------------------------------------------- |
| Can be instantiated | No         | Unknown status | No           | Forbidden         | Forbidden             | none                | [repo-update.schema.json*](../../out/repo-update.schema.json "open original schema") |

## ^.\*$ Type

`object` ([Branch's Commits](repo-update-properties-update-data-properties-target-repos-patternproperties-repo-and-commits-properties-commits-by-branches-patternproperties-branchs-commits.md))

# ^.\*$ Properties

| Property                            | Type     | Required | Nullable       | Defined by                                                                                                                                                                                                                                                                                                                                                                                 |
| :---------------------------------- | :------- | :------- | :------------- | :----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| [before_pull](#before_pull)         | `object` | Required | cannot be null | [Repository Handlers Input](repo-update-definitions-commit-sha-and-custom-information.md "repo_update.schema.json#/properties/update/properties/target_repos/patternProperties/^.*$/properties/commits/patternProperties/^.*$/properties/before_pull")                                                                                                                                     |
| [after_pull](#after_pull)           | `object` | Required | cannot be null | [Repository Handlers Input](repo-update-definitions-commit-sha-and-custom-information.md "repo_update.schema.json#/properties/update/properties/target_repos/patternProperties/^.*$/properties/commits/patternProperties/^.*$/properties/after_pull")                                                                                                                                      |
| [new](#new)                         | `array`  | Required | cannot be null | [Repository Handlers Input](repo-update-properties-update-data-properties-target-repos-patternproperties-repo-and-commits-properties-commits-by-branches-patternproperties-branchs-commits-properties-new.md "repo_update.schema.json#/properties/update/properties/target_repos/patternProperties/^.*$/properties/commits/patternProperties/^.*$/properties/new")                         |
| [unauthenticated](#unauthenticated) | `array`  | Required | cannot be null | [Repository Handlers Input](repo-update-properties-update-data-properties-target-repos-patternproperties-repo-and-commits-properties-commits-by-branches-patternproperties-branchs-commits-properties-unauthenticated.md "repo_update.schema.json#/properties/update/properties/target_repos/patternProperties/^.*$/properties/commits/patternProperties/^.*$/properties/unauthenticated") |

## before_pull

Repository's top commit before pull

`before_pull`

*   is required

*   Type: `object` ([Commit SHA and Custom Information](repo-update-definitions-commit-sha-and-custom-information.md))

*   cannot be null

*   defined in: [Repository Handlers Input](repo-update-definitions-commit-sha-and-custom-information.md "repo_update.schema.json#/properties/update/properties/target_repos/patternProperties/^.\*$/properties/commits/patternProperties/^.\*$/properties/before_pull")

### before_pull Type

`object` ([Commit SHA and Custom Information](repo-update-definitions-commit-sha-and-custom-information.md))

## after_pull

Repository's top commit after pull

`after_pull`

*   is required

*   Type: `object` ([Commit SHA and Custom Information](repo-update-definitions-commit-sha-and-custom-information.md))

*   cannot be null

*   defined in: [Repository Handlers Input](repo-update-definitions-commit-sha-and-custom-information.md "repo_update.schema.json#/properties/update/properties/target_repos/patternProperties/^.\*$/properties/commits/patternProperties/^.\*$/properties/after_pull")

### after_pull Type

`object` ([Commit SHA and Custom Information](repo-update-definitions-commit-sha-and-custom-information.md))

## new

A list of new authenticated commits (specified in target files of the authentication repository)

`new`

*   is required

*   Type: `object[]` ([Commit SHA and Custom Information](repo-update-definitions-commit-sha-and-custom-information.md))

*   cannot be null

*   defined in: [Repository Handlers Input](repo-update-properties-update-data-properties-target-repos-patternproperties-repo-and-commits-properties-commits-by-branches-patternproperties-branchs-commits-properties-new.md "repo_update.schema.json#/properties/update/properties/target_repos/patternProperties/^.\*$/properties/commits/patternProperties/^.\*$/properties/new")

### new Type

`object[]` ([Commit SHA and Custom Information](repo-update-definitions-commit-sha-and-custom-information.md))

## unauthenticated

New unauthenticated commits - additional commits newer than the last authenticated commit in case of repositories where unauthenticated commits are allowed

`unauthenticated`

*   is required

*   Type: `string[]`

*   cannot be null

*   defined in: [Repository Handlers Input](repo-update-properties-update-data-properties-target-repos-patternproperties-repo-and-commits-properties-commits-by-branches-patternproperties-branchs-commits-properties-unauthenticated.md "repo_update.schema.json#/properties/update/properties/target_repos/patternProperties/^.\*$/properties/commits/patternProperties/^.\*$/properties/unauthenticated")

### unauthenticated Type

`string[]`

### unauthenticated Constraints

**unique items**: all items in this array must be unique. Duplicates are not allowed.
