definitions = {
    "repo_data": {
        "description": "All information about a git repository instance. Can be used to create a new object.",
        "type": "object",
        "title": "Git Repository",
        "properties": {
            "library_dir": {
                "title": "Library's Root Directory",
                "description": "Library's root directory. Repository's name is appended to it to form the full path",
                "type": "string",
            },
            "name": {
                "title": "Name",
                "description": "Repository's name, in namespace/repo_name format",
                "type": "string",
            },
            "urls": {
                "title": "URLs",
                "description": "A list of repository's urls",
                "type": "array",
                "items": {"type": "string"},
                "minItems": 1,
                "uniqueItems": True,
            },
            "custom": {
                "title": "Custom",
                "description": "Any additional information about the repository. Not used by the framework.",
                "type": "object",
            },
            "default_branch": {
                "title": "Default Branch",
                "description": "Name of the default branch, e.g. master or main",
                "type": "string",
            },
        },
        "required": ["library_dir", "name", "urls"],
    },
    "commit_with_custom": {
        "type": "object",
        "title": "Commit SHA and Custom Information",
        "properties": {
            "commit": {"description": "Commit SHA", "type": "string"},
            "custom": {
                "title": "Custom",
                "decription": "Additional custom information - can be anything that is useful for further processing. Not used by the framework.",
                "type": "object",
            },
        },
    },
}

auth_repo_schema = {
    "description": "All information about an authentication repository coupled with update details",
    "type": "object",
    "title": "Authentication Repository with Update Details",
    "properties": {
        "data": {
            "description": "All properties of the authentication repository. Can be used to instantiate the AuthenticationRepository",
            "title": "Auth Repo",
            "type": "object",
            "allOf": [{"$ref": "#/definitions/repo_data"}],
            "properties": {
                "library_dir": {"title": "Library's Root Directory"},
                "name": {"title": "Name"},
                "urls": {"title": "URLs"},
                "default_branch": {"title": "Default Branch"},
                "custom": {"title": "Custom"},
                "conf_directory_root": {
                    "title": "Configuration Directory's Parent Directory",
                    "description": "Path to the direcotry containing the configuration directory. The configuration direcotry contain last_validated_commit file and its name is equal to _repo_name",
                    "type": "string",
                },
                "out_of_band_authentication": {
                    "title": "Out of Band Authentication",
                    "description": "Commit used to check the authentication repository's validity. Supposed to be equal to the first commit",
                    "type": ["string", "null"],
                },
            },
            "required": ["library_dir", "name", "urls"],
            "additionalProperties": False,
        },
        "commits": {
            "description": "Information about commits - top commit before pull, pulled commits and top commit after pull",
            "type": "object",
            "title": "Commits",
            "properties": {
                "before_pull": {
                    "title" "description": "Repository's top commit before pull",
                    "type": ["string", "null"],
                },
                "new": {
                    "title": "Pulled Commits",
                    "type": "array",
                    "description": "A list of pulled (new) commits",
                    "items": {"type": "string"},
                    "uniqueItems": True,
                },
                "after_pull": {
                    "title": "Commit After Pull",
                    "description": "Repository's top commit before pull",
                    "type": ["string", "null"],
                },
            },
            "required": ["before_pull", "new", "after_pull"],
            "additionalProperties": False,
        },
    },
    "additionalProperties": False,
    "required": ["data", "commits"],
}

repo_update_schema = {
    "definitions": definitions,
    "type": "object",
    "$id": "repo_update.schema.json",
    "$schema": "http://json-schema.org/draft-07/schema#",
    "title": "Repository Handlers Input",
    "properties": {
        "update": {
            "description": "All information related to the update process of an authentication repository - updated repository and pulled commits",
            "type": "object",
            "title": "Update Data",
            "properties": {
                "changed": {
                    "title": "Change Indicator",
                    "description": "Indicates if the repository was updated or not (will be false if pull was successful, but there were no new commits)",
                    "type": "boolean",
                },
                "event": {
                    "title": "Update Event",
                    "description": "Update event type - succeeded, changed, unchanged, failed, completed",
                    "type": "string",
                },
                "repo_name": {
                    "title": "Name",
                    "description": "Name of the repository whose update was attempted",
                    "type": "string",
                },
                "error_msg": {
                    "title": "Error message",
                    "description": "Error message that was raised while updating the repository",
                    "type": "string",
                },
                "auth_repo": auth_repo_schema,
                "target_repos": {
                    "description": "Information about the authentication repository's target repositories, including the update details",
                    "type": "object",
                    "title": "Target Repos",
                    "patternProperties": {
                        "^.*$": {
                            "title": "Repo and Commits",
                            "type": "object",
                            "properties": {
                                "repo_data": {"$ref": "#/definitions/repo_data"},
                                "commits": {
                                    "title": "Commits by Branches",
                                    "type": "object",
                                    "patternProperties": {
                                        "^.*$": {
                                            "description": "Commit before pull, after pull and lists of new and unauthenticated commits belonging to the given branch",
                                            "type": "object",
                                            "title": "Branch's Commits",
                                            "properties": {
                                                "before_pull": {
                                                    "description": "Repository's top commit before pull",
                                                    "$ref": "#/definitions/commit_with_custom",
                                                },
                                                "after_pull": {
                                                    "description": "Repository's top commit after pull",
                                                    "$ref": "#/definitions/commit_with_custom",
                                                },
                                                "new": {
                                                    "description": "A list of new authenticated commits (specified in target files of the authentication repository)",
                                                    "type": "array",
                                                    "items": {
                                                        "$ref": "#/definitions/commit_with_custom",
                                                    },
                                                },
                                                "unauthenticated": {
                                                    "description": "New unauthenticated commits - additional commits newer than the last authenticated commit in case of repositories where unauthenticated commits are allowed",
                                                    "type": "array",
                                                    "items": {"type": "string"},
                                                    "uniqueItems": True,
                                                },
                                            },
                                            "additionalProperties": False,
                                            "required": [
                                                "before_pull",
                                                "after_pull",
                                                "new",
                                                "unauthenticated",
                                            ],
                                        }
                                    },
                                    "additionalProperties": False,
                                },
                            },
                            "required": ["repo_data", "commits"],
                            "additionalProperties": False,
                        }
                    },
                    "additionalProperties": False,
                },
                "custom": {
                    "title": "Custom",
                    "description": "Additional custom data. Not used by the framework.",
                    "type": "object",
                },
            },
            "required": [
                "changed",
                "event",
                "repo_name",
                "error_msg",
                "auth_repo",
                "target_repos",
            ],
            "additionalProperties": False,
        },
        "state": {
            "title": "State",
            "description": "Persistent and transient states",
            "type": "object",
            "properties": {
                "transient": {
                    "title": "Transient",
                    "type": "object",
                    "description": "Transient data is arbitrary data passed from one script execution to the next one. It is discarded at the end of the process",
                },
                "persistent": {
                    "title": "Persistent",
                    "type": "object",
                    "description": "Persistent data is arbitrary data passed from one script execution to the next one and saved to disk (to a file called persistent.json directly inside the library root)",
                },
            },
        },
        "config": {
            "description": "Additional configuration, loaded from config.json located inside the library root",
            "title": "Configuration Data",
            "type": "object",
        },
    },
    "required": ["update"],
    "additionalProperties": False,
}

update_update_schema = {
    "type": "object",
    "$id": "update_update.schema.json",
    "$schema": "http://json-schema.org/draft-07/schema#",
    "title": "Update Handlers Input",
    "properties": {
        "update": {
            "description": "All information related to the update process of update - last handler (containing all authentication repositories linked to all repositories)",
            "type": "object",
            "title": "Update data",
            "properties": {
                "changed": {
                    "title": "Change Indicator",
                    "description": "Indicates if at least one of the repositories was updated (will be false if pull was successful, but there were no new commits)",
                    "type": "boolean",
                },
                "event": {
                    "title": "Update Event",
                    "description": "Event type - succeeded, changed, unchanged, failed, completed",
                    "type": "string",
                },
                "error_msg": {
                    "title": "Error message",
                    "description": "Error message that was raised while updating the repositories",
                    "type": "string",
                },
                "auth_repos": {
                    "title": "Authentication Repositories with a flat structure",
                    "type": "object",
                    "items": {"$ref": "repo_update.schema.json#"},
                },
                "auth_repo_name": {
                    "title": "Name",
                    "description": "Name of authentication repository that was called by the updater",
                    "type": "string",
                },
            },
            "required": [
                "changed",
                "event",
                "error_msg",
                "auth_repos",
                "auth_repo_name",
            ],
            "additionalProperties": False,
        },
        "state": {
            "title": "State",
            "description": "Persistent and transient states",
            "type": "object",
            "properties": {
                "transient": {
                    "title": "Transient",
                    "type": "object",
                    "description": "Transient data is arbitrary data passed from one script execution to the next one. It is discarded at the end of the process",
                },
                "persistent": {
                    "title": "Persistent",
                    "type": "object",
                    "description": "Persistent data is arbitrary date passed from one script execution the next one and stored to disk (to a file called persistent.json directly inside the library root)",
                },
            },
        },
        "config": {
            "title": "Configuration data",
            "description": "Additional configuration, loaded from config.json located inside the library root",
            "type": "object",
        },
    },
    "required": ["update"],
    "additionalProperties": False,
}
