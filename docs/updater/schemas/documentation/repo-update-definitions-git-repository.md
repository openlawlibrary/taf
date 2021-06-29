# Git Repository Schema

```txt
repo_update.schema.json#/properties/update/properties/target_repos/patternProperties/^.*$/properties/repo_data
```

All information about a git repository instance. Can be used to create a new object.

| Abstract            | Extensible | Status         | Identifiable | Custom Properties | Additional Properties | Access Restrictions | Defined In                                                                        |
| :------------------ | :--------- | :------------- | :----------- | :---------------- | :-------------------- | :------------------ | :-------------------------------------------------------------------------------- |
| Can be instantiated | No         | Unknown status | No           | Forbidden         | Allowed               | none                | [repo-update.schema.json*](../out/repo-update.schema.json "open original schema") |

## repo_data Type

`object` ([Git Repository](repo-update-definitions-git-repository.md))

# repo_data Properties

| Property                          | Type     | Required | Nullable       | Defined by                                                                                                                                                                        |
| :-------------------------------- | :------- | :------- | :------------- | :-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| [library_dir](#library_dir)       | `string` | Required | cannot be null | [Repository Handlers Input](repo-update-definitions-git-repository-properties-librarys-root-directory.md "repo_update.schema.json#/definitions/repo_data/properties/library_dir") |
| [name](#name)                     | `string` | Required | cannot be null | [Repository Handlers Input](repo-update-definitions-git-repository-properties-name.md "repo_update.schema.json#/definitions/repo_data/properties/name")                           |
| [urls](#urls)                     | `array`  | Required | cannot be null | [Repository Handlers Input](repo-update-definitions-git-repository-properties-urls.md "repo_update.schema.json#/definitions/repo_data/properties/urls")                           |
| [custom](#custom)                 | `object` | Optional | cannot be null | [Repository Handlers Input](repo-update-definitions-git-repository-properties-custom.md "repo_update.schema.json#/definitions/repo_data/properties/custom")                       |
| [default_branch](#default_branch) | `string` | Optional | cannot be null | [Repository Handlers Input](repo-update-definitions-git-repository-properties-default-branch.md "repo_update.schema.json#/definitions/repo_data/properties/default_branch")       |

## library_dir



`library_dir`

*   is required

*   Type: `string` ([Library's Root Directory](repo-update-definitions-git-repository-properties-librarys-root-directory.md))

*   cannot be null

*   defined in: [Repository Handlers Input](repo-update-definitions-git-repository-properties-librarys-root-directory.md "repo_update.schema.json#/definitions/repo_data/properties/library_dir")

### library_dir Type

`string` ([Library's Root Directory](repo-update-definitions-git-repository-properties-librarys-root-directory.md))

## name

Repository's name, in namespace/repo_name format

`name`

*   is required

*   Type: `string` ([Name](repo-update-definitions-git-repository-properties-name.md))

*   cannot be null

*   defined in: [Repository Handlers Input](repo-update-definitions-git-repository-properties-name.md "repo_update.schema.json#/definitions/repo_data/properties/name")

### name Type

`string` ([Name](repo-update-definitions-git-repository-properties-name.md))

## urls

A list of repository's urls

`urls`

*   is required

*   Type: `string[]`

*   cannot be null

*   defined in: [Repository Handlers Input](repo-update-definitions-git-repository-properties-urls.md "repo_update.schema.json#/definitions/repo_data/properties/urls")

### urls Type

`string[]`

### urls Constraints

**minimum number of items**: the minimum number of items for this array is: `1`

**unique items**: all items in this array must be unique. Duplicates are not allowed.

## custom

Any additional information about the repository. Not used by the framework.

`custom`

*   is optional

*   Type: `object` ([Custom](repo-update-definitions-git-repository-properties-custom.md))

*   cannot be null

*   defined in: [Repository Handlers Input](repo-update-definitions-git-repository-properties-custom.md "repo_update.schema.json#/definitions/repo_data/properties/custom")

### custom Type

`object` ([Custom](repo-update-definitions-git-repository-properties-custom.md))

## default_branch

Name of the default branch, e.g. master or main

`default_branch`

*   is optional

*   Type: `string` ([Default Branch](repo-update-definitions-git-repository-properties-default-branch.md))

*   cannot be null

*   defined in: [Repository Handlers Input](repo-update-definitions-git-repository-properties-default-branch.md "repo_update.schema.json#/definitions/repo_data/properties/default_branch")

### default_branch Type

`string` ([Default Branch](repo-update-definitions-git-repository-properties-default-branch.md))
