# State Schema

```txt
repo_update.schema.json#/properties/state
```

Persistent and transient states

| Abstract            | Extensible | Status         | Identifiable | Custom Properties | Additional Properties | Access Restrictions | Defined In                                                                           |
| :------------------ | :--------- | :------------- | :----------- | :---------------- | :-------------------- | :------------------ | :----------------------------------------------------------------------------------- |
| Can be instantiated | No         | Unknown status | No           | Forbidden         | Allowed               | none                | [repo-update.schema.json*](../../out/repo-update.schema.json "open original schema") |

## state Type

`object` ([State](repo-update-properties-state.md))

# state Properties

| Property                  | Type     | Required | Nullable       | Defined by                                                                                                                                           |
| :------------------------ | :------- | :------- | :------------- | :--------------------------------------------------------------------------------------------------------------------------------------------------- |
| [transient](#transient)   | `object` | Optional | cannot be null | [Repository Handlers Input](repo-update-properties-state-properties-transient.md "repo_update.schema.json#/properties/state/properties/transient")   |
| [persistent](#persistent) | `object` | Optional | cannot be null | [Repository Handlers Input](repo-update-properties-state-properties-persistent.md "repo_update.schema.json#/properties/state/properties/persistent") |

## transient

Transient data is arbitrary data passed from one script execution to the next one. It is discarded at the end of the process

`transient`

*   is optional

*   Type: `object` ([Transient](repo-update-properties-state-properties-transient.md))

*   cannot be null

*   defined in: [Repository Handlers Input](repo-update-properties-state-properties-transient.md "repo_update.schema.json#/properties/state/properties/transient")

### transient Type

`object` ([Transient](repo-update-properties-state-properties-transient.md))

## persistent

Persistent data is arbitrary date passed from one script execution the next one and stored to disk (to a file called persistent.json directly inside the library root)

`persistent`

*   is optional

*   Type: `object` ([Persistent](repo-update-properties-state-properties-persistent.md))

*   cannot be null

*   defined in: [Repository Handlers Input](repo-update-properties-state-properties-persistent.md "repo_update.schema.json#/properties/state/properties/persistent")

### persistent Type

`object` ([Persistent](repo-update-properties-state-properties-persistent.md))
