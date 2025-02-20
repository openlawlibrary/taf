MESSAGES = {
    "git-commit": {
        "create-repo": "Initialize repository",
        "add-dependency": "Add new dependency {dependency_name}",
        "remove-dependency": "Remove dependency {dependency_name}",
        "add-target": "Add new target {target_name}",
        "remove-target": "Remove target {target_name}",
        "remove-from-delegated-paths": "Remove {target_name} from delegated paths",
        "update-targets": "Sign targets and metadata",
        "update-expiration-dates": "Update expiration date of {roles}",
        "add-role": "Add new role {role}",
        "remove-role": "Remove role {role}",
        "add-role-paths": "Delegate path(s) {paths} to role {role}",
        "add-roles": "Add new roles {roles}",
        "add-signing-key": "Add new signing key to role {role}",
        "remove-role-paths": "Remove delegations {paths} from role {role}",
        "add-key-names": "Add key names",
    }
}


def git_commit_message(key, **kwargs):
    if not len(kwargs):
        return MESSAGES["git-commit"][key]
    return MESSAGES["git-commit"][key].format(**kwargs)
