
MESSAGES = {
    "git-commit": {
        "create-repo": "Initialized repository",
        "add-dependency": "Add new dependency {dependency_name}",
        "remove-dependency": "Remove dependency {dependency_name}",
        "add-target": "Add new target {target_name}",
        "remove-target": "Remove target {target_name}",
        "remove-from-delegated-paths": "Remove {target_name} from delegated paths",
    }
}

def git_commit_message(key, **kwargs):
    if not len(kwargs):
        return MESSAGES["git-commit"][key]
    return MESSAGES["git-commit"][key].format(**kwargs)
