# Hosts Schema

```txt
repo_update.schema.json#/properties/update/properties/auth_repo/properties/data/properties/hosts
```

A dictionary mapping host names to additional information about them.

| Abstract            | Extensible | Status         | Identifiable            | Custom Properties | Additional Properties | Access Restrictions | Defined In                                                                           |
| :------------------ | :--------- | :------------- | :---------------------- | :---------------- | :-------------------- | :------------------ | :----------------------------------------------------------------------------------- |
| Can be instantiated | No         | Unknown status | Unknown identifiability | Forbidden         | Allowed               | none                | [repo-update.schema.json*](../../out/repo-update.schema.json "open original schema") |

## hosts Type

`object` ([Hosts](repo-update-properties-update-data-properties-auth-repo-with-update-details-properties-auth-repo-properties-hosts.md))

# hosts Properties

| Property | Type     | Required | Nullable       | Defined by                                                                                                                                                                                                                                                                                                               |
| :------- | :------- | :------- | :------------- | :----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `^.*$`   | `object` | Optional | cannot be null | [Repository Handlers Input](repo-update-properties-update-data-properties-auth-repo-with-update-details-properties-auth-repo-properties-hosts-patternproperties-host-name-with-custom-info.md "repo_update.schema.json#/properties/update/properties/auth_repo/properties/data/properties/hosts/patternProperties/^.*$") |

## Pattern: `^.*$`



`^.*$`

*   is optional

*   Type: `object` ([Host Name with Custom Info](repo-update-properties-update-data-properties-auth-repo-with-update-details-properties-auth-repo-properties-hosts-patternproperties-host-name-with-custom-info.md))

*   cannot be null

*   defined in: [Repository Handlers Input](repo-update-properties-update-data-properties-auth-repo-with-update-details-properties-auth-repo-properties-hosts-patternproperties-host-name-with-custom-info.md "repo_update.schema.json#/properties/update/properties/auth_repo/properties/data/properties/hosts/patternProperties/^.\*$")

### ^.\*$ Type

`object` ([Host Name with Custom Info](repo-update-properties-update-data-properties-auth-repo-with-update-details-properties-auth-repo-properties-hosts-patternproperties-host-name-with-custom-info.md))
