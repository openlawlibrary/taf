definitions = {
    "repo_data": {
        "description": "All information about a GitRepository instance. Can be used to create a new object.",
        "type": "object",
        "title": "GitRepository",
        "properties": {
            "library_dir": {
                "descirption": "Library's root directory. Repository's name is appended to it to form the full path",
                "type": "string",
            },
            "name": {
                "description": "Repository's name, in namespace/repo_name format",
                "type": "string",
            },
            "urls": {
                "description": "A list of repository's urls",
                "type": "array",
                "items": {"type": "string"},
                "minItems": 1,
                "uniqueItems": True,
            },
            "custom": {
                "description": "Any additional information about the repository. Not used by the framework.",
                "type": "object",
            },
            "default_branch": {
                "description": "Name of the default branch, e.g. master or main",
                "type": "string",
            },
        },
        "required": ["library_dir", "name", "urls"],
    },
    "commit_with_custom": {
        "type": "object",
        "title": "Commit SHA and custom information",
        "properties": {
            "commit": {"description": "Commit SHA", "type": "string"},
            "custom": {
                "decription": "Additional custom information - can be anything that is useful for further processing. Not used by the framework.",
                "type": "object",
            },
        },
    },
}

auth_repo_schema = {
    "description": "All information about a AuthenticationRepository coupled with update details",
    "type": "object",
    "title": "Authentication repository with update details",
    "properties": {
        "data": {
            "description": "All properties of the authentication repository. Can be used to instantiate the AuthenticationRepository",
            "title": "AuthenticationRepository",
            "type": "object",
            "allOf": [{"$ref": "#/definitions/repo_data"}],
            "properties": {
                "library_dir": {},
                "name": {},
                "urls": {},
                "default_branch": {},
                "custom": {},
                "conf_directory_root": {
                    "description": "Path to the direcotry containing the configuration directory. The configuration direcotry contain last_validated_commit file and its name is equal to _repo_name",
                    "type": "string",
                },
                "out_of_band_authentication": {
                    "description": "Commit used to check the authentication repository's validity. Supposed to be uqual to the first commit",
                    "type": ["string", "null"],
                },
                "hosts": {
                    "description": "A dictionary mapping host names to additional information about them.",
                    "title": "Hosts",
                    "type": "object",
                    "patternProperties": {
                        "^.*$": {
                            "title": "Host name with additional information",
                            "type": "object",
                            "properties": {
                                "custom": {
                                    "descirption": "Any information required for futher processing. Not used by the framework",
                                    "type": "object",
                                }
                            },
                            "additionalProperties": False,
                        },
                    },
                },
            },
            "required": ["library_dir", "name", "urls"],
            "additionalProperties": False,
        },
        "commits": {
            "description": "Information about commits - top commit before pull, pulled commits and top commit after pull",
            "type": "object",
            "title": "Authentication repository's commits",
            "properties": {
                "before_pull": {
                    "description": "Repository's top commit before pull",
                    "type": ["string", "null"],
                },
                "new": {
                    "type": "array",
                    "description": "A list of pulled (new) commits",
                    "items": {"type": "string"},
                    "uniqueItems": True,
                },
                "after_pull": {
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
    "title": "Repository handler's schema",
    "properties": {
        "update": {
            "description": "All information related to the update process of an authentication repository - updated repository and pulled commits",
            "type": "object",
            "title": "Authentication repository's update data",
            "properties": {
                "changed": {
                    "description": "Indicates if the repository was updated or not (will be false if pull was successful, but there were no new commits)",
                    "type": "boolean",
                },
                "event": {
                    "description": "Update event type - succeeded, changed, unchanged, failed, completed",
                    "type": "string",
                },
                "repo_name": {
                    "description": "Name of the repository whose update was attempted",
                    "type": "string",
                },
                "error_msg": {
                    "description": "Error message that was raised while updating the repository",
                    "type": "string",
                },
                "auth_repo": auth_repo_schema,
                "target_repos": {
                    "description": "Information about the authentication repository's target repositories, including the update details",
                    "type": "object",
                    "title": "Target repositories' update information",
                    "patternProperties": {
                        "^.*$": {
                            "description": "Target repository's pulled commits per branches",
                            "type": "object",
                            "properties": {
                                "repo_data": {"$ref": "#/definitions/repo_data"},
                                "commits": {
                                    "description": "Commits per branches",
                                    "type": "object",
                                    "patternProperties": {
                                        "^.*$": {
                                            "description": "Commit before pull, after pull and lists of new and unauthenticated commits belonging to the given branch",
                                            "type": "object",
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
                    "type": "object",
                    "description": "Transient data is arbitrary data passed from one script execution to the next one. It is discarded at the end of the process"
                },
                "persistent": {
                    "type": "object",
                    "description": "Persistent data is arbitrary date passed from one script execution the next one and stored to disk (to a file called persistent.json directly inside the library root)"
                },
            },
        },
        "config": {
            "description": "Additional configuration, loaded from config.json located inside the library root",
            "title": "Configuration data",
            "type": "object",
        },
    },
    "required": ["update"],
    "additionalProperties": False,
}


host_update_schema = {
    "type": "object",
    "$id": "host_update.schema.json",
    "$schema": "http://json-schema.org/draft-07/schema#",
    "title": "Host handler's schema",
    "properties": {
        "update": {
            "description": "All information related to the update process of a host (containing all authentication repositories linked to that host)",
            "type": "object",
            "title": "Host's update data",
            "properties": {
                "changed": {
                    "description": "Indicates if at least one of the host's repositories was updated (will be false if pull was successful, but there were no new commits)",
                    "type": "boolean",
                },
                "event": {
                    "description": "Event type - succeeded, changed, unchanged, failed, completed",
                    "type": "string",
                },
                "host_name": {
                    "description": "Name of the host whose update was attempted",
                    "type": "string",
                },
                "error_msg": {
                    "description": "Error message that was raised while updating the host's repositories",
                    "type": "string",
                },
                "auth_repos": {
                    "type": "array",
                    "items": {
                        "$ref": "repo_update.schema.json#"
                    }
                },
                "custom": {
                    "description": "Additional host data. Not used by the framework",
                    "type": "object",
                },
            },
            "required": ["changed", "event", "host_name", "error_msg", "auth_repos"],
            "additionalProperties": False,
        },
        "state": {
            "title": "State",
            "description": "Persistent and transient states",
            "type": "object",
            "properties": {
                "transient": {
                    "type": "object",
                    "description": "Transient data is arbitrary data passed from one script execution to the next one. It is discarded at the end of the process"
                },
                "persistent": {
                    "type": "object",
                    "description": "Persistent data is arbitrary date passed from one script execution the next one and stored to disk (to a file called persistent.json directly inside the library root)"
                },
            },
        },
        "config": {
            "description": "Additional configuration, loaded from config.json located inside the library root",
            "type": "object",
        },
    },
    "required": ["update"],
    "additionalProperties": False,
}
