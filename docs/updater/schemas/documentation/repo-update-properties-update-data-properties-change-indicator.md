# Change Indicator Schema

```txt
repo_update.schema.json#/properties/update/properties/changed
```

Indicates if the repository was updated or not (will be false if pull was successful, but there were no new commits)

| Abstract            | Extensible | Status         | Identifiable            | Custom Properties | Additional Properties | Access Restrictions | Defined In                                                                        |
| :------------------ | :--------- | :------------- | :---------------------- | :---------------- | :-------------------- | :------------------ | :-------------------------------------------------------------------------------- |
| Can be instantiated | No         | Unknown status | Unknown identifiability | Forbidden         | Allowed               | none                | [repo-update.schema.json*](../out/repo-update.schema.json "open original schema") |

## changed Type

`boolean` ([Change Indicator](repo-update-properties-update-data-properties-change-indicator.md))
