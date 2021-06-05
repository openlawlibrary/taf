
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
        "required":["library_dir", "name", "urls"],
        "additionalProperties": False,
    },
    "commits_data": {
        "description": "Information about commits - top commit before pull, pulled commits and top commit after pull",
        "type": "object",
        "properties": {
            "before_pull": {
                "description": "Repository's top commit before pull",
                "type": ["string", "null"]
            },
            "new": {
                "type": "array",
                "description": "A list of pulled (new) commits",
                "items": {"type": "string"},
                "uniqueItems": True,
            },
            "after_pull": {
                "description": "Repository's top commit before pull",
                "type": ["string", "null"]
            },
        },
        "required": ["before_pull", "new", "after_pull"],
        "additionalProperties": False,
    },
}
auth_repo_schema = {
    "description": "Information about the repository with pull details",
    "type": "object",
    "properties": {
        "data": {
            "description": "All properties of the authentication repository. Can be used to instantiate the AuthenticationRepository using from_json_dict",
            "type": "object",
            "allOf": [
                { "$ref": "#/definitions/repo_data"},
                {"properties": {
                    "conf_directory_root": {
                        "description": "Path to the directory which contains the config directory",
                        "type": "string",
                    },
                    "out_of_band_authentication": {
                        "description": "Commit used to check repository's validity. Supposed to be uqual to the first commit",
                        "type":  ["string", "null"]
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
                                        "type": "object"
                                    }
                                },
                                "additionalProperties": False,
                            },
                        },
                    },
                },
                    "additionalProperties": False,
                }
                    ]
                },
                "commits": {"$ref": "#/definitions/commits_data"},
                "target_repos": {
                    "description": "Information about the authentication repository's target repositories, including pull data",
                    "type": "object",
                    "properties": {
                        "data": { "$ref": "#/definitions/repo_data"},
                        "commits": {
                            "description": "Commits per branches",
                            "type": "object",
                            "patternProperties": {
                                "^.*$": { "$ref": "#/definitions/commits_data"}
                        },
                        "additionalProperties": False,
                    }
                }
            },
    }
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
                    "description": "Error message that was raised while updating the F.json located inside the library root) after every execution"
                },
                "auth_repo": auth_repo_schema
            },
        },
        "config": {
            "description": "Additional configuration, loaded from config.json located inside the library root",
            "type": "object",
        },
    }
}
