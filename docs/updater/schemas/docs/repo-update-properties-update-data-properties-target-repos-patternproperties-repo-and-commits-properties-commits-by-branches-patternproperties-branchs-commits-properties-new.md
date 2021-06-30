# Untitled array in Repository Handlers Input Schema

```txt
repo_update.schema.json#/properties/update/properties/target_repos/patternProperties/^.*$/properties/commits/patternProperties/^.*$/properties/new
```

A list of new authenticated commits (specified in target files of the authentication repository)

| Abstract            | Extensible | Status         | Identifiable            | Custom Properties | Additional Properties | Access Restrictions | Defined In                                                                           |
| :------------------ | :--------- | :------------- | :---------------------- | :---------------- | :-------------------- | :------------------ | :----------------------------------------------------------------------------------- |
| Can be instantiated | No         | Unknown status | Unknown identifiability | Forbidden         | Allowed               | none                | [repo-update.schema.json*](docs/repo-update.schema.json "open original schema") |

## new Type

`object[]` ([Commit SHA and Custom Information](repo-update-definitions-commit-sha-and-custom-information.md))
