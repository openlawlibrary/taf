# Update data Schema

```txt
host_update.schema.json#/properties/update
```

All information related to the update process of a host (containing all authentication repositories linked to that host)

| Abstract            | Extensible | Status         | Identifiable | Custom Properties | Additional Properties | Access Restrictions | Defined In                                                                           |
| :------------------ | :--------- | :------------- | :----------- | :---------------- | :-------------------- | :------------------ | :----------------------------------------------------------------------------------- |
| Can be instantiated | No         | Unknown status | No           | Forbidden         | Forbidden             | none                | [host-update.schema.json*](../../out/host-update.schema.json "open original schema") |

## update Type

`object` ([Update data](host-update-properties-update-data.md))

# update Properties

| Property                  | Type      | Required | Nullable       | Defined by                                                                                                                                                             |
| :------------------------ | :-------- | :------- | :------------- | :--------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| [changed](#changed)       | `boolean` | Required | cannot be null | [Host Handlers Input](host-update-properties-update-data-properties-change-indicator.md "host_update.schema.json#/properties/update/properties/changed")               |
| [event](#event)           | `string`  | Required | cannot be null | [Host Handlers Input](host-update-properties-update-data-properties-update-event.md "host_update.schema.json#/properties/update/properties/event")                     |
| [host_name](#host_name)   | `string`  | Required | cannot be null | [Host Handlers Input](host-update-properties-update-data-properties-name.md "host_update.schema.json#/properties/update/properties/host_name")                         |
| [error_msg](#error_msg)   | `string`  | Required | cannot be null | [Host Handlers Input](host-update-properties-update-data-properties-error-message.md "host_update.schema.json#/properties/update/properties/error_msg")                |
| [auth_repos](#auth_repos) | `array`   | Required | cannot be null | [Host Handlers Input](host-update-properties-update-data-properties-authentication-repositories.md "host_update.schema.json#/properties/update/properties/auth_repos") |
| [custom](#custom)         | `object`  | Optional | cannot be null | [Host Handlers Input](host-update-properties-update-data-properties-custom.md "host_update.schema.json#/properties/update/properties/custom")                          |

## changed

Indicates if at least one of the host's repositories was updated (will be false if pull was successful, but there were no new commits)

`changed`

*   is required

*   Type: `boolean` ([Change Indicator](host-update-properties-update-data-properties-change-indicator.md))

*   cannot be null

*   defined in: [Host Handlers Input](host-update-properties-update-data-properties-change-indicator.md "host_update.schema.json#/properties/update/properties/changed")

### changed Type

`boolean` ([Change Indicator](host-update-properties-update-data-properties-change-indicator.md))

## event

Event type - succeeded, changed, unchanged, failed, completed

`event`

*   is required

*   Type: `string` ([Update Event](host-update-properties-update-data-properties-update-event.md))

*   cannot be null

*   defined in: [Host Handlers Input](host-update-properties-update-data-properties-update-event.md "host_update.schema.json#/properties/update/properties/event")

### event Type

`string` ([Update Event](host-update-properties-update-data-properties-update-event.md))

## host_name

Name of the host whose update was attempted

`host_name`

*   is required

*   Type: `string` ([Name](host-update-properties-update-data-properties-name.md))

*   cannot be null

*   defined in: [Host Handlers Input](host-update-properties-update-data-properties-name.md "host_update.schema.json#/properties/update/properties/host_name")

### host_name Type

`string` ([Name](host-update-properties-update-data-properties-name.md))

## error_msg

Error message that was raised while updating the host's repositories

`error_msg`

*   is required

*   Type: `string` ([Error message](host-update-properties-update-data-properties-error-message.md))

*   cannot be null

*   defined in: [Host Handlers Input](host-update-properties-update-data-properties-error-message.md "host_update.schema.json#/properties/update/properties/error_msg")

### error_msg Type

`string` ([Error message](host-update-properties-update-data-properties-error-message.md))

## auth_repos



`auth_repos`

*   is required

*   Type: `object[]` ([Repository Handlers Input](host-update-properties-update-data-properties-authentication-repositories-repository-handlers-input.md))

*   cannot be null

*   defined in: [Host Handlers Input](host-update-properties-update-data-properties-authentication-repositories.md "host_update.schema.json#/properties/update/properties/auth_repos")

### auth_repos Type

`object[]` ([Repository Handlers Input](host-update-properties-update-data-properties-authentication-repositories-repository-handlers-input.md))

## custom

Additional host data. Not used by the framework

`custom`

*   is optional

*   Type: `object` ([Custom](host-update-properties-update-data-properties-custom.md))

*   cannot be null

*   defined in: [Host Handlers Input](host-update-properties-update-data-properties-custom.md "host_update.schema.json#/properties/update/properties/custom")

### custom Type

`object` ([Custom](host-update-properties-update-data-properties-custom.md))
