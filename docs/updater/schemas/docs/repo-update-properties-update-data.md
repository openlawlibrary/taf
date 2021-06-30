# Update Data Schema

```txt
repo_update.schema.json#/properties/update
```

All information related to the update process of an authentication repository - updated repository and pulled commits

| Abstract            | Extensible | Status         | Identifiable | Custom Properties | Additional Properties | Access Restrictions | Defined In                                                                           |
| :------------------ | :--------- | :------------- | :----------- | :---------------- | :-------------------- | :------------------ | :----------------------------------------------------------------------------------- |
| Can be instantiated | No         | Unknown status | No           | Forbidden         | Forbidden             | none                | [repo-update.schema.json*](../../out/repo-update.schema.json "open original schema") |

## update Type

`object` ([Update Data](repo-update-properties-update-data.md))

# update Properties

| Property                      | Type      | Required | Nullable       | Defined by                                                                                                                                                                    |
| :---------------------------- | :-------- | :------- | :------------- | :---------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| [changed](#changed)           | `boolean` | Required | cannot be null | [Repository Handlers Input](repo-update-properties-update-data-properties-change-indicator.md "repo_update.schema.json#/properties/update/properties/changed")                |
| [event](#event)               | `string`  | Required | cannot be null | [Repository Handlers Input](repo-update-properties-update-data-properties-update-event.md "repo_update.schema.json#/properties/update/properties/event")                      |
| [repo_name](#repo_name)       | `string`  | Required | cannot be null | [Repository Handlers Input](repo-update-properties-update-data-properties-name.md "repo_update.schema.json#/properties/update/properties/repo_name")                          |
| [error_msg](#error_msg)       | `string`  | Required | cannot be null | [Repository Handlers Input](repo-update-properties-update-data-properties-error-message.md "repo_update.schema.json#/properties/update/properties/error_msg")                 |
| [auth_repo](#auth_repo)       | `object`  | Required | cannot be null | [Repository Handlers Input](repo-update-properties-update-data-properties-auth-repo-with-update-details.md "repo_update.schema.json#/properties/update/properties/auth_repo") |
| [target_repos](#target_repos) | `object`  | Required | cannot be null | [Repository Handlers Input](repo-update-properties-update-data-properties-target-repos.md "repo_update.schema.json#/properties/update/properties/target_repos")               |
| [custom](#custom)             | `object`  | Optional | cannot be null | [Repository Handlers Input](repo-update-properties-update-data-properties-custom.md "repo_update.schema.json#/properties/update/properties/custom")                           |

## changed

Indicates if the repository was updated or not (will be false if pull was successful, but there were no new commits)

`changed`

*   is required

*   Type: `boolean` ([Change Indicator](repo-update-properties-update-data-properties-change-indicator.md))

*   cannot be null

*   defined in: [Repository Handlers Input](repo-update-properties-update-data-properties-change-indicator.md "repo_update.schema.json#/properties/update/properties/changed")

### changed Type

`boolean` ([Change Indicator](repo-update-properties-update-data-properties-change-indicator.md))

## event

Update event type - succeeded, changed, unchanged, failed, completed

`event`

*   is required

*   Type: `string` ([Update Event](repo-update-properties-update-data-properties-update-event.md))

*   cannot be null

*   defined in: [Repository Handlers Input](repo-update-properties-update-data-properties-update-event.md "repo_update.schema.json#/properties/update/properties/event")

### event Type

`string` ([Update Event](repo-update-properties-update-data-properties-update-event.md))

## repo_name

Name of the repository whose update was attempted

`repo_name`

*   is required

*   Type: `string` ([Name](repo-update-properties-update-data-properties-name.md))

*   cannot be null

*   defined in: [Repository Handlers Input](repo-update-properties-update-data-properties-name.md "repo_update.schema.json#/properties/update/properties/repo_name")

### repo_name Type

`string` ([Name](repo-update-properties-update-data-properties-name.md))

## error_msg

Error message that was raised while updating the repository

`error_msg`

*   is required

*   Type: `string` ([Error message](repo-update-properties-update-data-properties-error-message.md))

*   cannot be null

*   defined in: [Repository Handlers Input](repo-update-properties-update-data-properties-error-message.md "repo_update.schema.json#/properties/update/properties/error_msg")

### error_msg Type

`string` ([Error message](repo-update-properties-update-data-properties-error-message.md))

## auth_repo

All information about an authentication repository coupled with update details

`auth_repo`

*   is required

*   Type: `object` ([Auth Repo with Update Details](repo-update-properties-update-data-properties-auth-repo-with-update-details.md))

*   cannot be null

*   defined in: [Repository Handlers Input](repo-update-properties-update-data-properties-auth-repo-with-update-details.md "repo_update.schema.json#/properties/update/properties/auth_repo")

### auth_repo Type

`object` ([Auth Repo with Update Details](repo-update-properties-update-data-properties-auth-repo-with-update-details.md))

## target_repos

Information about the authentication repository's target repositories, including the update details

`target_repos`

*   is required

*   Type: `object` ([Target Repos](repo-update-properties-update-data-properties-target-repos.md))

*   cannot be null

*   defined in: [Repository Handlers Input](repo-update-properties-update-data-properties-target-repos.md "repo_update.schema.json#/properties/update/properties/target_repos")

### target_repos Type

`object` ([Target Repos](repo-update-properties-update-data-properties-target-repos.md))

## custom

Additional custom data. Not used by the framework.

`custom`

*   is optional

*   Type: `object` ([Custom](repo-update-properties-update-data-properties-custom.md))

*   cannot be null

*   defined in: [Repository Handlers Input](repo-update-properties-update-data-properties-custom.md "repo_update.schema.json#/properties/update/properties/custom")

### custom Type

`object` ([Custom](repo-update-properties-update-data-properties-custom.md))
