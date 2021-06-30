# Auth Repo Schema

```txt
repo_update.schema.json#/properties/update/properties/auth_repo/properties/data
```

All properties of the authentication repository. Can be used to instantiate the AuthenticationRepository

| Abstract            | Extensible | Status         | Identifiable | Custom Properties | Additional Properties | Access Restrictions | Defined In                                                                           |
| :------------------ | :--------- | :------------- | :----------- | :---------------- | :-------------------- | :------------------ | :----------------------------------------------------------------------------------- |
| Can be instantiated | No         | Unknown status | No           | Forbidden         | Forbidden             | none                | [repo-update.schema.json*](docs/repo-update.schema.json "open original schema") |

## data Type

`object` ([Auth Repo](repo-update-properties-update-data-properties-auth-repo-with-update-details-properties-auth-repo.md))

all of

*   [Git Repository](repo-update-definitions-git-repository.md "check type definition")

# data Properties

| Property                                                  | Type          | Required | Nullable       | Defined by                                                                                                                                                                                                                                                                                             |
| :-------------------------------------------------------- | :------------ | :------- | :------------- | :----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| [library_dir](#library_dir)                               | Not specified | Required | cannot be null | [Repository Handlers Input](repo-update-properties-update-data-properties-auth-repo-with-update-details-properties-auth-repo-properties-librarys-root-directory.md "repo_update.schema.json#/properties/update/properties/auth_repo/properties/data/properties/library_dir")                           |
| [name](#name)                                             | Not specified | Required | cannot be null | [Repository Handlers Input](repo-update-properties-update-data-properties-auth-repo-with-update-details-properties-auth-repo-properties-name.md "repo_update.schema.json#/properties/update/properties/auth_repo/properties/data/properties/name")                                                     |
| [urls](#urls)                                             | Not specified | Required | cannot be null | [Repository Handlers Input](repo-update-properties-update-data-properties-auth-repo-with-update-details-properties-auth-repo-properties-urls.md "repo_update.schema.json#/properties/update/properties/auth_repo/properties/data/properties/urls")                                                     |
| [default_branch](#default_branch)                         | Not specified | Optional | cannot be null | [Repository Handlers Input](repo-update-properties-update-data-properties-auth-repo-with-update-details-properties-auth-repo-properties-default-branch.md "repo_update.schema.json#/properties/update/properties/auth_repo/properties/data/properties/default_branch")                                 |
| [custom](#custom)                                         | Not specified | Optional | cannot be null | [Repository Handlers Input](repo-update-properties-update-data-properties-auth-repo-with-update-details-properties-auth-repo-properties-custom.md "repo_update.schema.json#/properties/update/properties/auth_repo/properties/data/properties/custom")                                                 |
| [conf_directory_root](#conf_directory_root)               | `string`      | Optional | cannot be null | [Repository Handlers Input](repo-update-properties-update-data-properties-auth-repo-with-update-details-properties-auth-repo-properties-configuration-directorys-parent-directory.md "repo_update.schema.json#/properties/update/properties/auth_repo/properties/data/properties/conf_directory_root") |
| [out_of_band_authentication](#out_of_band_authentication) | `string`      | Optional | can be null    | [Repository Handlers Input](repo-update-properties-update-data-properties-auth-repo-with-update-details-properties-auth-repo-properties-out-of-band-authentication.md "repo_update.schema.json#/properties/update/properties/auth_repo/properties/data/properties/out_of_band_authentication")         |
| [hosts](#hosts)                                           | `object`      | Optional | cannot be null | [Repository Handlers Input](repo-update-properties-update-data-properties-auth-repo-with-update-details-properties-auth-repo-properties-hosts.md "repo_update.schema.json#/properties/update/properties/auth_repo/properties/data/properties/hosts")                                                   |

## library_dir



`library_dir`

*   is required

*   Type: unknown ([Library's Root Directory](repo-update-properties-update-data-properties-auth-repo-with-update-details-properties-auth-repo-properties-librarys-root-directory.md))

*   cannot be null

*   defined in: [Repository Handlers Input](repo-update-properties-update-data-properties-auth-repo-with-update-details-properties-auth-repo-properties-librarys-root-directory.md "repo_update.schema.json#/properties/update/properties/auth_repo/properties/data/properties/library_dir")

### library_dir Type

unknown ([Library's Root Directory](repo-update-properties-update-data-properties-auth-repo-with-update-details-properties-auth-repo-properties-librarys-root-directory.md))

## name



`name`

*   is required

*   Type: unknown ([Name](repo-update-properties-update-data-properties-auth-repo-with-update-details-properties-auth-repo-properties-name.md))

*   cannot be null

*   defined in: [Repository Handlers Input](repo-update-properties-update-data-properties-auth-repo-with-update-details-properties-auth-repo-properties-name.md "repo_update.schema.json#/properties/update/properties/auth_repo/properties/data/properties/name")

### name Type

unknown ([Name](repo-update-properties-update-data-properties-auth-repo-with-update-details-properties-auth-repo-properties-name.md))

## urls



`urls`

*   is required

*   Type: unknown ([URLs](repo-update-properties-update-data-properties-auth-repo-with-update-details-properties-auth-repo-properties-urls.md))

*   cannot be null

*   defined in: [Repository Handlers Input](repo-update-properties-update-data-properties-auth-repo-with-update-details-properties-auth-repo-properties-urls.md "repo_update.schema.json#/properties/update/properties/auth_repo/properties/data/properties/urls")

### urls Type

unknown ([URLs](repo-update-properties-update-data-properties-auth-repo-with-update-details-properties-auth-repo-properties-urls.md))

## default_branch



`default_branch`

*   is optional

*   Type: unknown ([Default Branch](repo-update-properties-update-data-properties-auth-repo-with-update-details-properties-auth-repo-properties-default-branch.md))

*   cannot be null

*   defined in: [Repository Handlers Input](repo-update-properties-update-data-properties-auth-repo-with-update-details-properties-auth-repo-properties-default-branch.md "repo_update.schema.json#/properties/update/properties/auth_repo/properties/data/properties/default_branch")

### default_branch Type

unknown ([Default Branch](repo-update-properties-update-data-properties-auth-repo-with-update-details-properties-auth-repo-properties-default-branch.md))

## custom



`custom`

*   is optional

*   Type: unknown ([Custom](repo-update-properties-update-data-properties-auth-repo-with-update-details-properties-auth-repo-properties-custom.md))

*   cannot be null

*   defined in: [Repository Handlers Input](repo-update-properties-update-data-properties-auth-repo-with-update-details-properties-auth-repo-properties-custom.md "repo_update.schema.json#/properties/update/properties/auth_repo/properties/data/properties/custom")

### custom Type

unknown ([Custom](repo-update-properties-update-data-properties-auth-repo-with-update-details-properties-auth-repo-properties-custom.md))

## conf_directory_root

Path to the direcotry containing the configuration directory. The configuration direcotry contain last_validated_commit file and its name is equal to \_repo_name

`conf_directory_root`

*   is optional

*   Type: `string` ([Configuration Directory's Parent Directory](repo-update-properties-update-data-properties-auth-repo-with-update-details-properties-auth-repo-properties-configuration-directorys-parent-directory.md))

*   cannot be null

*   defined in: [Repository Handlers Input](repo-update-properties-update-data-properties-auth-repo-with-update-details-properties-auth-repo-properties-configuration-directorys-parent-directory.md "repo_update.schema.json#/properties/update/properties/auth_repo/properties/data/properties/conf_directory_root")

### conf_directory_root Type

`string` ([Configuration Directory's Parent Directory](repo-update-properties-update-data-properties-auth-repo-with-update-details-properties-auth-repo-properties-configuration-directorys-parent-directory.md))

## out_of_band_authentication

Commit used to check the authentication repository's validity. Supposed to be uqual to the first commit

`out_of_band_authentication`

*   is optional

*   Type: `string` ([Out of Band Authentication](repo-update-properties-update-data-properties-auth-repo-with-update-details-properties-auth-repo-properties-out-of-band-authentication.md))

*   can be null

*   defined in: [Repository Handlers Input](repo-update-properties-update-data-properties-auth-repo-with-update-details-properties-auth-repo-properties-out-of-band-authentication.md "repo_update.schema.json#/properties/update/properties/auth_repo/properties/data/properties/out_of_band_authentication")

### out_of_band_authentication Type

`string` ([Out of Band Authentication](repo-update-properties-update-data-properties-auth-repo-with-update-details-properties-auth-repo-properties-out-of-band-authentication.md))

## hosts

A dictionary mapping host names to additional information about them.

`hosts`

*   is optional

*   Type: `object` ([Hosts](repo-update-properties-update-data-properties-auth-repo-with-update-details-properties-auth-repo-properties-hosts.md))

*   cannot be null

*   defined in: [Repository Handlers Input](repo-update-properties-update-data-properties-auth-repo-with-update-details-properties-auth-repo-properties-hosts.md "repo_update.schema.json#/properties/update/properties/auth_repo/properties/data/properties/hosts")

### hosts Type

`object` ([Hosts](repo-update-properties-update-data-properties-auth-repo-with-update-details-properties-auth-repo-properties-hosts.md))
