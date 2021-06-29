# State Schema

```txt
host_update.schema.json#/properties/state
```

Persistent and transient states

| Abstract            | Extensible | Status         | Identifiable | Custom Properties | Additional Properties | Access Restrictions | Defined In                                                                        |
| :------------------ | :--------- | :------------- | :----------- | :---------------- | :-------------------- | :------------------ | :-------------------------------------------------------------------------------- |
| Can be instantiated | No         | Unknown status | No           | Forbidden         | Allowed               | none                | [host-update.schema.json*](../out/host-update.schema.json "open original schema") |

## state Type

`object` ([State](host-update-properties-state.md))

# state Properties

| Property                  | Type     | Required | Nullable       | Defined by                                                                                                                                     |
| :------------------------ | :------- | :------- | :------------- | :--------------------------------------------------------------------------------------------------------------------------------------------- |
| [transient](#transient)   | `object` | Optional | cannot be null | [Host Handlers Input](host-update-properties-state-properties-transient.md "host_update.schema.json#/properties/state/properties/transient")   |
| [persistent](#persistent) | `object` | Optional | cannot be null | [Host Handlers Input](host-update-properties-state-properties-persistent.md "host_update.schema.json#/properties/state/properties/persistent") |

## transient

Transient data is arbitrary data passed from one script execution to the next one. It is discarded at the end of the process

`transient`

*   is optional

*   Type: `object` ([Transient](host-update-properties-state-properties-transient.md))

*   cannot be null

*   defined in: [Host Handlers Input](host-update-properties-state-properties-transient.md "host_update.schema.json#/properties/state/properties/transient")

### transient Type

`object` ([Transient](host-update-properties-state-properties-transient.md))

## persistent

Persistent data is arbitrary date passed from one script execution the next one and stored to disk (to a file called persistent.json directly inside the library root)

`persistent`

*   is optional

*   Type: `object` ([Persistent](host-update-properties-state-properties-persistent.md))

*   cannot be null

*   defined in: [Host Handlers Input](host-update-properties-state-properties-persistent.md "host_update.schema.json#/properties/state/properties/persistent")

### persistent Type

`object` ([Persistent](host-update-properties-state-properties-persistent.md))
