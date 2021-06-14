# Untitled array in Repository Handlers Input Schema

```txt
repo_update.schema.json#/properties/update/properties/target_repos/patternProperties/^.*$/properties/commits/patternProperties/^.*$/properties/unauthenticated
```

New unauthenticated commits - additional commits newer than the last authenticated commit in case of repositories where unauthenticated commits are allowed

| Abstract            | Extensible | Status         | Identifiable            | Custom Properties | Additional Properties | Access Restrictions | Defined In                                                                        |
| :------------------ | :--------- | :------------- | :---------------------- | :---------------- | :-------------------- | :------------------ | :-------------------------------------------------------------------------------- |
| Can be instantiated | No         | Unknown status | Unknown identifiability | Forbidden         | Allowed               | none                | [repo-update.schema.json*](../out/repo-update.schema.json "open original schema") |

## unauthenticated Type

`string[]`

## unauthenticated Constraints

**unique items**: all items in this array must be unique. Duplicates are not allowed.
