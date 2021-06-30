# Host Handlers Input Schema

```txt
host_update.schema.json
```



| Abstract            | Extensible | Status         | Identifiable | Custom Properties | Additional Properties | Access Restrictions | Defined In                                                                          |
| :------------------ | :--------- | :------------- | :----------- | :---------------- | :-------------------- | :------------------ | :---------------------------------------------------------------------------------- |
| Can be instantiated | No         | Unknown status | No           | Forbidden         | Forbidden             | none                | [host-update.schema.json](docs/host-update.schema.json "open original schema") |

## Host Handlers Input Type

`object` ([Host Handlers Input](host-update.md))

# Host Handlers Input Properties

| Property          | Type     | Required | Nullable       | Defined by                                                                                                       |
| :---------------- | :------- | :------- | :------------- | :--------------------------------------------------------------------------------------------------------------- |
| [update](#update) | `object` | Required | cannot be null | [Host Handlers Input](host-update-properties-update-data.md "host_update.schema.json#/properties/update")        |
| [state](#state)   | `object` | Optional | cannot be null | [Host Handlers Input](host-update-properties-state.md "host_update.schema.json#/properties/state")               |
| [config](#config) | `object` | Optional | cannot be null | [Host Handlers Input](host-update-properties-configuration-data.md "host_update.schema.json#/properties/config") |

## update

All information related to the update process of a host (containing all authentication repositories linked to that host)

`update`

*   is required

*   Type: `object` ([Update data](host-update-properties-update-data.md))

*   cannot be null

*   defined in: [Host Handlers Input](host-update-properties-update-data.md "host_update.schema.json#/properties/update")

### update Type

`object` ([Update data](host-update-properties-update-data.md))

## state

Persistent and transient states

`state`

*   is optional

*   Type: `object` ([State](host-update-properties-state.md))

*   cannot be null

*   defined in: [Host Handlers Input](host-update-properties-state.md "host_update.schema.json#/properties/state")

### state Type

`object` ([State](host-update-properties-state.md))

## config

Additional configuration, loaded from config.json located inside the library root

`config`

*   is optional

*   Type: `object` ([Configuration data](host-update-properties-configuration-data.md))

*   cannot be null

*   defined in: [Host Handlers Input](host-update-properties-configuration-data.md "host_update.schema.json#/properties/config")

### config Type

`object` ([Configuration data](host-update-properties-configuration-data.md))
