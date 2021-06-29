# Change Indicator Schema

```txt
host_update.schema.json#/properties/update/properties/changed
```

Indicates if at least one of the host's repositories was updated (will be false if pull was successful, but there were no new commits)

| Abstract            | Extensible | Status         | Identifiable            | Custom Properties | Additional Properties | Access Restrictions | Defined In                                                                        |
| :------------------ | :--------- | :------------- | :---------------------- | :---------------- | :-------------------- | :------------------ | :-------------------------------------------------------------------------------- |
| Can be instantiated | No         | Unknown status | Unknown identifiability | Forbidden         | Allowed               | none                | [host-update.schema.json*](../out/host-update.schema.json "open original schema") |

## changed Type

`boolean` ([Change Indicator](host-update-properties-update-data-properties-change-indicator.md))
