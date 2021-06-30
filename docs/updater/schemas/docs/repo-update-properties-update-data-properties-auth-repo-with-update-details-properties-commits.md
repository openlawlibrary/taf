# Commits Schema

```txt
repo_update.schema.json#/properties/update/properties/auth_repo/properties/commits
```

Information about commits - top commit before pull, pulled commits and top commit after pull

| Abstract            | Extensible | Status         | Identifiable | Custom Properties | Additional Properties | Access Restrictions | Defined In                                                                           |
| :------------------ | :--------- | :------------- | :----------- | :---------------- | :-------------------- | :------------------ | :----------------------------------------------------------------------------------- |
| Can be instantiated | No         | Unknown status | No           | Forbidden         | Forbidden             | none                | [repo-update.schema.json*](docs/repo-update.schema.json "open original schema") |

## commits Type

`object` ([Commits](repo-update-properties-update-data-properties-auth-repo-with-update-details-properties-commits.md))

# commits Properties

| Property                    | Type     | Required | Nullable       | Defined by                                                                                                                                                                                                                                                             |
| :-------------------------- | :------- | :------- | :------------- | :--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| [before_pull](#before_pull) | `string` | Required | can be null    | [Repository Handlers Input](repo-update-properties-update-data-properties-auth-repo-with-update-details-properties-commits-properties-before_pull.md "repo_update.schema.json#/properties/update/properties/auth_repo/properties/commits/properties/before_pull")      |
| [new](#new)                 | `array`  | Required | cannot be null | [Repository Handlers Input](repo-update-properties-update-data-properties-auth-repo-with-update-details-properties-commits-properties-pulled-commits.md "repo_update.schema.json#/properties/update/properties/auth_repo/properties/commits/properties/new")           |
| [after_pull](#after_pull)   | `string` | Required | can be null    | [Repository Handlers Input](repo-update-properties-update-data-properties-auth-repo-with-update-details-properties-commits-properties-commit-after-pull.md "repo_update.schema.json#/properties/update/properties/auth_repo/properties/commits/properties/after_pull") |

## before_pull



`before_pull`

*   is required

*   Type: `string`

*   can be null

*   defined in: [Repository Handlers Input](repo-update-properties-update-data-properties-auth-repo-with-update-details-properties-commits-properties-before_pull.md "repo_update.schema.json#/properties/update/properties/auth_repo/properties/commits/properties/before_pull")

### before_pull Type

`string`

## new

A list of pulled (new) commits

`new`

*   is required

*   Type: `string[]`

*   cannot be null

*   defined in: [Repository Handlers Input](repo-update-properties-update-data-properties-auth-repo-with-update-details-properties-commits-properties-pulled-commits.md "repo_update.schema.json#/properties/update/properties/auth_repo/properties/commits/properties/new")

### new Type

`string[]`

### new Constraints

**unique items**: all items in this array must be unique. Duplicates are not allowed.

## after_pull

Repository's top commit before pull

`after_pull`

*   is required

*   Type: `string` ([Commit After Pull](repo-update-properties-update-data-properties-auth-repo-with-update-details-properties-commits-properties-commit-after-pull.md))

*   can be null

*   defined in: [Repository Handlers Input](repo-update-properties-update-data-properties-auth-repo-with-update-details-properties-commits-properties-commit-after-pull.md "repo_update.schema.json#/properties/update/properties/auth_repo/properties/commits/properties/after_pull")

### after_pull Type

`string` ([Commit After Pull](repo-update-properties-update-data-properties-auth-repo-with-update-details-properties-commits-properties-commit-after-pull.md))
