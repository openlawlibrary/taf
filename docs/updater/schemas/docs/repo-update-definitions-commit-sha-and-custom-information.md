# Commit SHA and Custom Information Schema

```txt
repo_update.schema.json#/properties/update/properties/target_repos/patternProperties/^.*$/properties/commits/patternProperties/^.*$/properties/new/items
```



| Abstract            | Extensible | Status         | Identifiable | Custom Properties | Additional Properties | Access Restrictions | Defined In                                                                           |
| :------------------ | :--------- | :------------- | :----------- | :---------------- | :-------------------- | :------------------ | :----------------------------------------------------------------------------------- |
| Can be instantiated | No         | Unknown status | No           | Forbidden         | Allowed               | none                | [repo-update.schema.json*](docs/repo-update.schema.json "open original schema") |

## items Type

`object` ([Commit SHA and Custom Information](repo-update-definitions-commit-sha-and-custom-information.md))

# items Properties

| Property          | Type     | Required | Nullable       | Defined by                                                                                                                                                                              |
| :---------------- | :------- | :------- | :------------- | :-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| [commit](#commit) | `string` | Optional | cannot be null | [Repository Handlers Input](repo-update-definitions-commit-sha-and-custom-information-properties-commit.md "repo_update.schema.json#/definitions/commit_with_custom/properties/commit") |
| [custom](#custom) | `object` | Optional | cannot be null | [Repository Handlers Input](repo-update-definitions-commit-sha-and-custom-information-properties-custom.md "repo_update.schema.json#/definitions/commit_with_custom/properties/custom") |

## commit

Commit SHA

`commit`

*   is optional

*   Type: `string`

*   cannot be null

*   defined in: [Repository Handlers Input](repo-update-definitions-commit-sha-and-custom-information-properties-commit.md "repo_update.schema.json#/definitions/commit_with_custom/properties/commit")

### commit Type

`string`

## custom



`custom`

*   is optional

*   Type: `object` ([Custom](repo-update-definitions-commit-sha-and-custom-information-properties-custom.md))

*   cannot be null

*   defined in: [Repository Handlers Input](repo-update-definitions-commit-sha-and-custom-information-properties-custom.md "repo_update.schema.json#/definitions/commit_with_custom/properties/custom")

### custom Type

`object` ([Custom](repo-update-definitions-commit-sha-and-custom-information-properties-custom.md))
