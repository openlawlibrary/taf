definitions = {
    "repo_data": {
        "description": "Contains all properties of a GitRepository object",
        "type": "object",
        "properties": {
            "library_dir": {
                "descirption": "Library's root directory. Repository's name is appended to it to form the full name",
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
                "description": "Additional information about the repository",
                "type": "object",
            },
            "default_branch": {
                "description": "Repository's default git branch, like master or main",
                "type": "string",
            },
        },
        "required": ["library_dir", "name", "urls"],
    },
    "commit_with_custom": {
        "description": "Commit SHA with an optional custom dictionary",
        "type": "object",
        "properties": {
            "commit": {
                "description": "Commit SHA",
                "type": "string"
            },
            "custom": {
                "decription": "Additional custom information - can be anything that is useful for further processing",
                "type": "object"
            }
        }
    }
}
auth_repo_schema = {
    "description": "Information about the repository with pull details",
    "type": "object",
    "properties": {
        "data": {
            "description": "All properties of the authentication repository. Can be used to instantiate the AuthenticationRepository using from_json_dict",
            "type": "object",
            "allOf": [{"$ref": "#/definitions/repo_data"}],
            "properties": {
                "library_dir": {},
                "name": {},
                "urls": {},
                "default_branch": {},
                "custom": {},
                "conf_directory_root": {
                    "description": "Path to the directory which contains the config directory",
                    "type": "string",
                },
                "out_of_band_authentication": {
                    "description": "Commit used to check repository's validity. Supposed to be uqual to the first commit",
                    "type": ["string", "null"],
                },
                "hosts": {
                    "description": "A dictionary mapping host names to additional information about them. Extracted from dependencies.json",
                    "type": "object",
                    "patternProperties": {
                        "^.*$": {
                            "description": "Host name with additional information",
                            "type": "object",
                            "properties": {
                                "custom": {
                                    "descirption": "Any information required for futher processing",
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
    "required": ["data", "commits"]
}

update_schema = {
    "definitions": definitions,
    "type": "object",
    "properties": {
        "update": {
            "description": "A collection of all information related to the update process - updated repository and pulled commits",
            "type": "object",
            "properties": {
                "changed": {
                    "description": "Indicator if the repository was updated or not",
                    "type": "boolean",
                },
                "event": {
                    "description": "Event type - succeeded, changed, unchanged, failed, completed",
                    "type": "string",
                },
                "repo_name": {
                    "description": "Name of the repository whose update was attempted",
                    "type": "string",
                },
                "error_msg": {
                    "description": "Error message that was raised while updating the repository"
                },
                "auth_repo": auth_repo_schema,
                "target_repos": {
                    "description": "Information about the authentication repository's target repositories, including pull data",
                    "type": "object",
                    "patternProperties": {
                        "^.*$": {
                            "description": "Target repository's name and information about it and the pulled commits",
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
                                                "before_pull": {"$ref": "#/definitions/commit_with_custom"},
                                                "after_pull": {"$ref": "#/definitions/commit_with_custom"},
                                                "new": {
                                                    "description": "New authenticated commits",
                                                    "type": "array"
                                                },
                                                "unauthenticated": {
                                                    "description": "New unauthenticated commits - additional commits newer than the last authenticated commit in case of repositories where unauthenticated commits are allowed",
                                                    "type": "array",
                                                    "items": {"type": "string"},
                                                    "uniqueItems": True,
                                                }
                                            },
                                            "additionalProperties": False,
                                            "required": ["before_pull", "after_pull", "new", "unauthenticated"]
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
                }
            },
            "required": ["changed", "event", "repo_name", "error_msg", "auth_repo", "target_repos"],
            "additionalProperties": False,
        },
        "state": {
            "type": "object",
            "properties": {
                "transient": {
                    "type": "object"
                },
                "persistent": {
                    "type": "object"
                }
            }
        },
        "config": {
            "description": "Additional configuration, loaded from config.json located inside the library root",
            "type": "object",
        },
    },
    "required": ["update", "state", "config"],
    "additionalProperties": False,
}
