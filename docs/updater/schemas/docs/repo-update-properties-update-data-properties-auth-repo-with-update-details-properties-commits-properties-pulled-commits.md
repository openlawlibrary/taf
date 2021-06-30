# Pulled Commits Schema

```txt
repo_update.schema.json#/properties/update/properties/auth_repo/properties/commits/properties/new
```

A list of pulled (new) commits

| Abstract            | Extensible | Status         | Identifiable            | Custom Properties | Additional Properties | Access Restrictions | Defined In                                                                           |
| :------------------ | :--------- | :------------- | :---------------------- | :---------------- | :-------------------- | :------------------ | :----------------------------------------------------------------------------------- |
| Can be instantiated | No         | Unknown status | Unknown identifiability | Forbidden         | Allowed               | none                | [repo-update.schema.json*](../../out/repo-update.schema.json "open original schema") |

## new Type

`string[]`

## new Constraints

**unique items**: all items in this array must be unique. Duplicates are not allowed.
