# Repo and Commits Schema

```txt
repo_update.schema.json#/properties/update/properties/target_repos/patternProperties/^.*$
```



| Abstract            | Extensible | Status         | Identifiable | Custom Properties | Additional Properties | Access Restrictions | Defined In                                                                           |
| :------------------ | :--------- | :------------- | :----------- | :---------------- | :-------------------- | :------------------ | :----------------------------------------------------------------------------------- |
| Can be instantiated | No         | Unknown status | No           | Forbidden         | Forbidden             | none                | [repo-update.schema.json*](docs/repo-update.schema.json "open original schema") |

## ^.\*$ Type

`object` ([Repo and Commits](repo-update-properties-update-data-properties-target-repos-patternproperties-repo-and-commits.md))

# ^.\*$ Properties

| Property                | Type     | Required | Nullable       | Defined by                                                                                                                                                                                                                                                                  |
| :---------------------- | :------- | :------- | :------------- | :-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| [repo_data](#repo_data) | `object` | Required | cannot be null | [Repository Handlers Input](repo-update-definitions-git-repository.md "repo_update.schema.json#/properties/update/properties/target_repos/patternProperties/^.*$/properties/repo_data")                                                                                     |
| [commits](#commits)     | `object` | Required | cannot be null | [Repository Handlers Input](repo-update-properties-update-data-properties-target-repos-patternproperties-repo-and-commits-properties-commits-by-branches.md "repo_update.schema.json#/properties/update/properties/target_repos/patternProperties/^.*$/properties/commits") |

## repo_data

All information about a git repository instance. Can be used to create a new object.

`repo_data`

*   is required

*   Type: `object` ([Git Repository](repo-update-definitions-git-repository.md))

*   cannot be null

*   defined in: [Repository Handlers Input](repo-update-definitions-git-repository.md "repo_update.schema.json#/properties/update/properties/target_repos/patternProperties/^.\*$/properties/repo_data")

### repo_data Type

`object` ([Git Repository](repo-update-definitions-git-repository.md))

## commits



`commits`

*   is required

*   Type: `object` ([Commits by Branches](repo-update-properties-update-data-properties-target-repos-patternproperties-repo-and-commits-properties-commits-by-branches.md))

*   cannot be null

*   defined in: [Repository Handlers Input](repo-update-properties-update-data-properties-target-repos-patternproperties-repo-and-commits-properties-commits-by-branches.md "repo_update.schema.json#/properties/update/properties/target_repos/patternProperties/^.\*$/properties/commits")

### commits Type

`object` ([Commits by Branches](repo-update-properties-update-data-properties-target-repos-patternproperties-repo-and-commits-properties-commits-by-branches.md))
