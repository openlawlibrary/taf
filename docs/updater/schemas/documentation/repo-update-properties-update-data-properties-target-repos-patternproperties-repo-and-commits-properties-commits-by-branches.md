# Commits by Branches Schema

```txt
repo_update.schema.json#/properties/update/properties/target_repos/patternProperties/^.*$/properties/commits
```



| Abstract            | Extensible | Status         | Identifiable            | Custom Properties | Additional Properties | Access Restrictions | Defined In                                                                        |
| :------------------ | :--------- | :------------- | :---------------------- | :---------------- | :-------------------- | :------------------ | :-------------------------------------------------------------------------------- |
| Can be instantiated | No         | Unknown status | Unknown identifiability | Forbidden         | Forbidden             | none                | [repo-update.schema.json*](../out/repo-update.schema.json "open original schema") |

## commits Type

`object` ([Commits by Branches](repo-update-properties-update-data-properties-target-repos-patternproperties-repo-and-commits-properties-commits-by-branches.md))

# commits Properties

| Property | Type     | Required | Nullable       | Defined by                                                                                                                                                                                                                                                                                                                           |
| :------- | :------- | :------- | :------------- | :----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `^.*$`   | `object` | Optional | cannot be null | [Repository Handlers Input](repo-update-properties-update-data-properties-target-repos-patternproperties-repo-and-commits-properties-commits-by-branches-patternproperties-branchs-commits.md "repo_update.schema.json#/properties/update/properties/target_repos/patternProperties/^.*$/properties/commits/patternProperties/^.*$") |

## Pattern: `^.*$`

Commit before pull, after pull and lists of new and unauthenticated commits belonging to the given branch

`^.*$`

*   is optional

*   Type: `object` ([Branch's Commits](repo-update-properties-update-data-properties-target-repos-patternproperties-repo-and-commits-properties-commits-by-branches-patternproperties-branchs-commits.md))

*   cannot be null

*   defined in: [Repository Handlers Input](repo-update-properties-update-data-properties-target-repos-patternproperties-repo-and-commits-properties-commits-by-branches-patternproperties-branchs-commits.md "repo_update.schema.json#/properties/update/properties/target_repos/patternProperties/^.\*$/properties/commits/patternProperties/^.\*$")

### ^.\*$ Type

`object` ([Branch's Commits](repo-update-properties-update-data-properties-target-repos-patternproperties-repo-and-commits-properties-commits-by-branches-patternproperties-branchs-commits.md))
