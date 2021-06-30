# Repository Handlers Input Schema

```txt
repo_update.schema.json#/properties/update/properties/auth_repos/items
```



| Abstract            | Extensible | Status         | Identifiable | Custom Properties | Additional Properties | Access Restrictions | Defined In                                                                           |
| :------------------ | :--------- | :------------- | :----------- | :---------------- | :-------------------- | :------------------ | :----------------------------------------------------------------------------------- |
| Can be instantiated | Yes        | Unknown status | No           | Forbidden         | Forbidden             | none                | [host-update.schema.json*](../../out/host-update.schema.json "open original schema") |

## items Type

`object` ([Repository Handlers Input](host-update-properties-update-data-properties-authentication-repositories-repository-handlers-input.md))

# items Properties

| Property          | Type     | Required | Nullable       | Defined by                                                                                                             |
| :---------------- | :------- | :------- | :------------- | :--------------------------------------------------------------------------------------------------------------------- |
| [update](#update) | `object` | Required | cannot be null | [Repository Handlers Input](repo-update-properties-update-data.md "repo_update.schema.json#/properties/update")        |
| [state](#state)   | `object` | Optional | cannot be null | [Repository Handlers Input](repo-update-properties-state.md "repo_update.schema.json#/properties/state")               |
| [config](#config) | `object` | Optional | cannot be null | [Repository Handlers Input](repo-update-properties-configuration-data.md "repo_update.schema.json#/properties/config") |

## update

All information related to the update process of an authentication repository - updated repository and pulled commits

`update`

*   is required

*   Type: `object` ([Update Data](repo-update-properties-update-data.md))

*   cannot be null

*   defined in: [Repository Handlers Input](repo-update-properties-update-data.md "repo_update.schema.json#/properties/update")

### update Type

`object` ([Update Data](repo-update-properties-update-data.md))

## state

Persistent and transient states

`state`

*   is optional

*   Type: `object` ([State](repo-update-properties-state.md))

*   cannot be null

*   defined in: [Repository Handlers Input](repo-update-properties-state.md "repo_update.schema.json#/properties/state")

### state Type

`object` ([State](repo-update-properties-state.md))

## config

Additional configuration, loaded from config.json located inside the library root

`config`

*   is optional

*   Type: `object` ([Configuration Data](repo-update-properties-configuration-data.md))

*   cannot be null

*   defined in: [Repository Handlers Input](repo-update-properties-configuration-data.md "repo_update.schema.json#/properties/config")

### config Type

`object` ([Configuration Data](repo-update-properties-configuration-data.md))

# Repository Handlers Input Definitions

## Definitions group repo_data

Reference this group by using

```json
{"$ref":"repo_update.schema.json#/definitions/repo_data"}
```

| Property                          | Type     | Required | Nullable       | Defined by                                                                                                                                                                        |
| :-------------------------------- | :------- | :------- | :------------- | :-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| [library_dir](#library_dir)       | `string` | Required | cannot be null | [Repository Handlers Input](repo-update-definitions-git-repository-properties-librarys-root-directory.md "repo_update.schema.json#/definitions/repo_data/properties/library_dir") |
| [name](#name)                     | `string` | Required | cannot be null | [Repository Handlers Input](repo-update-definitions-git-repository-properties-name.md "repo_update.schema.json#/definitions/repo_data/properties/name")                           |
| [urls](#urls)                     | `array`  | Required | cannot be null | [Repository Handlers Input](repo-update-definitions-git-repository-properties-urls.md "repo_update.schema.json#/definitions/repo_data/properties/urls")                           |
| [custom](#custom)                 | `object` | Optional | cannot be null | [Repository Handlers Input](repo-update-definitions-git-repository-properties-custom.md "repo_update.schema.json#/definitions/repo_data/properties/custom")                       |
| [default_branch](#default_branch) | `string` | Optional | cannot be null | [Repository Handlers Input](repo-update-definitions-git-repository-properties-default-branch.md "repo_update.schema.json#/definitions/repo_data/properties/default_branch")       |

### library_dir



`library_dir`

*   is required

*   Type: `string` ([Library's Root Directory](repo-update-definitions-git-repository-properties-librarys-root-directory.md))

*   cannot be null

*   defined in: [Repository Handlers Input](repo-update-definitions-git-repository-properties-librarys-root-directory.md "repo_update.schema.json#/definitions/repo_data/properties/library_dir")

#### library_dir Type

`string` ([Library's Root Directory](repo-update-definitions-git-repository-properties-librarys-root-directory.md))

### name

Repository's name, in namespace/repo_name format

`name`

*   is required

*   Type: `string` ([Name](repo-update-definitions-git-repository-properties-name.md))

*   cannot be null

*   defined in: [Repository Handlers Input](repo-update-definitions-git-repository-properties-name.md "repo_update.schema.json#/definitions/repo_data/properties/name")

#### name Type

`string` ([Name](repo-update-definitions-git-repository-properties-name.md))

### urls

A list of repository's urls

`urls`

*   is required

*   Type: `string[]`

*   cannot be null

*   defined in: [Repository Handlers Input](repo-update-definitions-git-repository-properties-urls.md "repo_update.schema.json#/definitions/repo_data/properties/urls")

#### urls Type

`string[]`

#### urls Constraints

**minimum number of items**: the minimum number of items for this array is: `1`

**unique items**: all items in this array must be unique. Duplicates are not allowed.

### custom

Any additional information about the repository. Not used by the framework.

`custom`

*   is optional

*   Type: `object` ([Custom](repo-update-definitions-git-repository-properties-custom.md))

*   cannot be null

*   defined in: [Repository Handlers Input](repo-update-definitions-git-repository-properties-custom.md "repo_update.schema.json#/definitions/repo_data/properties/custom")

#### custom Type

`object` ([Custom](repo-update-definitions-git-repository-properties-custom.md))

### default_branch

Name of the default branch, e.g. master or main

`default_branch`

*   is optional

*   Type: `string` ([Default Branch](repo-update-definitions-git-repository-properties-default-branch.md))

*   cannot be null

*   defined in: [Repository Handlers Input](repo-update-definitions-git-repository-properties-default-branch.md "repo_update.schema.json#/definitions/repo_data/properties/default_branch")

#### default_branch Type

`string` ([Default Branch](repo-update-definitions-git-repository-properties-default-branch.md))

## Definitions group commit_with_custom

Reference this group by using

```json
{"$ref":"repo_update.schema.json#/definitions/commit_with_custom"}
```

| Property            | Type     | Required | Nullable       | Defined by                                                                                                                                                                              |
| :------------------ | :------- | :------- | :------------- | :-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| [commit](#commit)   | `string` | Optional | cannot be null | [Repository Handlers Input](repo-update-definitions-commit-sha-and-custom-information-properties-commit.md "repo_update.schema.json#/definitions/commit_with_custom/properties/commit") |
| [custom](#custom-1) | `object` | Optional | cannot be null | [Repository Handlers Input](repo-update-definitions-commit-sha-and-custom-information-properties-custom.md "repo_update.schema.json#/definitions/commit_with_custom/properties/custom") |

### commit

Commit SHA

`commit`

*   is optional

*   Type: `string`

*   cannot be null

*   defined in: [Repository Handlers Input](repo-update-definitions-commit-sha-and-custom-information-properties-commit.md "repo_update.schema.json#/definitions/commit_with_custom/properties/commit")

#### commit Type

`string`

### custom



`custom`

*   is optional

*   Type: `object` ([Custom](repo-update-definitions-commit-sha-and-custom-information-properties-custom.md))

*   cannot be null

*   defined in: [Repository Handlers Input](repo-update-definitions-commit-sha-and-custom-information-properties-custom.md "repo_update.schema.json#/definitions/commit_with_custom/properties/custom")

#### custom Type

`object` ([Custom](repo-update-definitions-commit-sha-and-custom-information-properties-custom.md))
