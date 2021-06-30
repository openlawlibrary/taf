# Auth Repo with Update Details Schema

```txt
repo_update.schema.json#/properties/update/properties/auth_repo
```

All information about an authentication repository coupled with update details

| Abstract            | Extensible | Status         | Identifiable | Custom Properties | Additional Properties | Access Restrictions | Defined In                                                                           |
| :------------------ | :--------- | :------------- | :----------- | :---------------- | :-------------------- | :------------------ | :----------------------------------------------------------------------------------- |
| Can be instantiated | No         | Unknown status | No           | Forbidden         | Forbidden             | none                | [repo-update.schema.json*](docs/repo-update.schema.json "open original schema") |

## auth_repo Type

`object` ([Auth Repo with Update Details](repo-update-properties-update-data-properties-auth-repo-with-update-details.md))

# auth_repo Properties

| Property            | Type     | Required | Nullable       | Defined by                                                                                                                                                                                                          |
| :------------------ | :------- | :------- | :------------- | :------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| [data](#data)       | Merged   | Required | cannot be null | [Repository Handlers Input](repo-update-properties-update-data-properties-auth-repo-with-update-details-properties-auth-repo.md "repo_update.schema.json#/properties/update/properties/auth_repo/properties/data")  |
| [commits](#commits) | `object` | Required | cannot be null | [Repository Handlers Input](repo-update-properties-update-data-properties-auth-repo-with-update-details-properties-commits.md "repo_update.schema.json#/properties/update/properties/auth_repo/properties/commits") |

## data

All properties of the authentication repository. Can be used to instantiate the AuthenticationRepository

`data`

*   is required

*   Type: `object` ([Auth Repo](repo-update-properties-update-data-properties-auth-repo-with-update-details-properties-auth-repo.md))

*   cannot be null

*   defined in: [Repository Handlers Input](repo-update-properties-update-data-properties-auth-repo-with-update-details-properties-auth-repo.md "repo_update.schema.json#/properties/update/properties/auth_repo/properties/data")

### data Type

`object` ([Auth Repo](repo-update-properties-update-data-properties-auth-repo-with-update-details-properties-auth-repo.md))

all of

*   [Git Repository](repo-update-definitions-git-repository.md "check type definition")

## commits

Information about commits - top commit before pull, pulled commits and top commit after pull

`commits`

*   is required

*   Type: `object` ([Commits](repo-update-properties-update-data-properties-auth-repo-with-update-details-properties-commits.md))

*   cannot be null

*   defined in: [Repository Handlers Input](repo-update-properties-update-data-properties-auth-repo-with-update-details-properties-commits.md "repo_update.schema.json#/properties/update/properties/auth_repo/properties/commits")

### commits Type

`object` ([Commits](repo-update-properties-update-data-properties-auth-repo-with-update-details-properties-commits.md))
