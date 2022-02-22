import enum
import glob
import json
import subprocess
from functools import partial
from pathlib import Path

import taf.settings as settings
from taf.repository_tool import get_target_path
from taf.utils import (
    run,
    safely_save_json_to_disk,
    extract_json_objects_from_trusted_stdout,
)
from taf.exceptions import ScriptExecutionError
from taf.log import taf_logger
from taf.updater.types.update import Update
from cattr import structure


class LifecycleStage(enum.Enum):
    REPO = "repo"
    HOST = "host"
    UPDATE = "update"


class Event(enum.Enum):
    SUCCEEDED = "succeeded"
    CHANGED = "changed"
    UNCHANGED = "unchanged"
    FAILED = "failed"
    COMPLETED = "completed"


CONFIG_NAME = "config.json"
SCRIPTS_DIR = "scripts"
PERSISTENT_FILE_NAME = "persistent.json"


# config should only be read once per library root
# make it flexible in case the updater needs to handle libraries with different roots
config_db = {}


# persistent data should be read from persistent file and updated after every handler call
# should be one file per library root


def _get_script_path(lifecycle_stage, event):
    if settings.development_mode:
        return f"{lifecycle_stage.value}/{event.value}"
    else:
        return Path(
            get_target_path(f"{SCRIPTS_DIR}/{lifecycle_stage.value}/{event.value}")
        )


def get_config(library_root, config_name=CONFIG_NAME):
    global config_db
    if library_root not in config_db:
        try:
            config = json.loads(Path(library_root, CONFIG_NAME).read_text())
        except Exception:
            config = {}
        config_db[library_root] = config or {}
    return config_db.get(library_root)


def get_persistent_data(library_root, persistent_file=PERSISTENT_FILE_NAME):
    persistent_file = Path(library_root, PERSISTENT_FILE_NAME)
    if not persistent_file.is_file():
        persistent_file.touch()

    try:
        return json.loads(persistent_file.read_text())
    except Exception:
        return {}


def _handle_event(
    lifecycle_stage,
    event,
    transient_data,
    library_dir,
    scripts_root_dir,
    *args,
    **kwargs,
):
    # read initial persistent data from file
    taf_logger.info("Called {} handler. Event: {}", lifecycle_stage, event.value)
    persistent_data = get_persistent_data(library_dir)
    transient_data = transient_data or {}
    prepare_data_name = f"prepare_data_{lifecycle_stage.value}"
    # expect a dictionary containing a map of the authentication repository whose
    # scripts should be invoked and data to be passed to those scripts
    repos_and_data = globals()[prepare_data_name](
        event, transient_data, persistent_data, library_dir, *args, **kwargs
    )

    def _execute_scripts(repos_and_data, lifecycle_stage, event):
        scripts_rel_path = _get_script_path(lifecycle_stage, event)
        # this will update data
        for script_repo, script_data in repos_and_data.items():
            data = script_data["data"]
            last_commit = script_data["commit"]
            repos_and_data[script_repo]["data"] = execute_scripts(
                script_repo, last_commit, scripts_rel_path, data, scripts_root_dir
            )
        return repos_and_data

    if event in (Event.CHANGED, Event.UNCHANGED, Event.SUCCEEDED):
        # if event is changed or unchanged, execute these scripts first, then call the succeeded script
        if event == Event.CHANGED:
            repos_and_data = _execute_scripts(repos_and_data, lifecycle_stage, event)
        elif event == Event.UNCHANGED:
            repos_and_data = _execute_scripts(repos_and_data, lifecycle_stage, event)

        repos_and_data = _execute_scripts(
            repos_and_data, lifecycle_stage, Event.SUCCEEDED
        )
    elif event == Event.FAILED:
        repos_and_data = _execute_scripts(repos_and_data, lifecycle_stage, event)

    # execute completed handler at the end
    # _print_data(repos_and_data, library_dir, lifecycle_stage)
    repos_and_data = _execute_scripts(repos_and_data, lifecycle_stage, Event.COMPLETED)

    # return formatted response if update lifecycle is done
    if lifecycle_stage == LifecycleStage.UPDATE:
        for _, data in repos_and_data.items():
            data = data["data"]["update"]
            # example of converting data to classes. for now we're using cattrs default converters.
            # TODO: goal is full support of class types
            return structure(data, Update)
    # return transient data as it should be propagated to other event and handlers
    return {
        repo.name: data["data"]["state"]["transient"]
        for repo, data in repos_and_data.items()
    }


handle_repo_event = partial(_handle_event, LifecycleStage.REPO)
handle_host_event = partial(_handle_event, LifecycleStage.HOST)
handle_update_event = partial(_handle_event, LifecycleStage.UPDATE)


def execute_scripts(auth_repo, last_commit, scripts_rel_path, data, scripts_root_dir):
    persistent_path = auth_repo.library_dir / PERSISTENT_FILE_NAME
    # do not load the script from the file system
    # the update might have failed because the repository contains an additional
    # commit with, say, malicious scripts
    # load the scripts from the last validated commit - whether new or old

    # this is a nightmare to test
    # load from filesystem in development mode so that the scripts can be updated without
    # having to commit and push
    development_mode = settings.development_mode

    if development_mode:
        if scripts_root_dir is not None:
            path = Path(scripts_root_dir) / auth_repo.name / scripts_rel_path
        else:
            path = Path(auth_repo.path) / scripts_rel_path
        script_paths = glob.glob(f"{path}/*.py")
    else:
        script_names = auth_repo.list_files_at_revision(last_commit, scripts_rel_path)
        script_rel_paths = [
            (scripts_rel_path / script_name).as_posix()
            for script_name in script_names
            if Path(script_name).suffix == ".py"
        ]
        auth_repo.checkout_paths(last_commit, *script_rel_paths)
        script_paths = [
            str(auth_repo.path / script_rel_path)
            for script_rel_path in script_rel_paths
        ]

    for script_path in sorted(script_paths):
        taf_logger.info("Executing script {}", script_path)
        json_data = json.dumps(data)
        try:
            output = run("py", script_path, input=json_data)
        except subprocess.CalledProcessError as e:
            taf_logger.error(
                "An error occurred while executing {}: {}", script_path, e.output
            )
            raise ScriptExecutionError(script_path, e.output)
        if output is not None and output != "":
            # if the script contains print statements other than the final
            # print which outputs transient and persistent data
            # meaning that we might not be able to convert output to a json
            # so try to locate jsons inside the output
            for json_data in extract_json_objects_from_trusted_stdout(output):
                transient_data = json_data.get("transient")
                persistent_data = json_data.get("persistent")
                if transient_data is not None or persistent_data is not None:
                    break
        else:
            transient_data = persistent_data = {}
        taf_logger.debug("Persistent data: {}", persistent_data)
        taf_logger.debug("Transient data: {}", transient_data)
        # overwrite current persistent and transient data
        data["state"]["transient"] = transient_data
        data["state"]["persistent"] = persistent_data
        try:
            # if persistent data is not a valid json or if an error happens while storing
            # to disk, raise an error
            # we save to disk by copying a temp file, so the likelihood of an error
            # should be decreased
            safely_save_json_to_disk(persistent_data, persistent_path)
        except Exception as e:
            raise ScriptExecutionError(
                script_path,
                f"An error occurred while saving persistent data to disk: {str(e)}",
            )
    return data


def get_script_repo_and_commit_repo(auth_repo, commits_data, *args):
    return auth_repo, commits_data["after_pull"]


def get_script_repo_and_commit_host(auth_repo, commits_data, *args):
    pass


def prepare_data_repo(
    event,
    transient_data,
    persistent_data,
    library_dir,
    auth_repo,
    commits_data,
    error,
    targets_data,
):
    return {
        auth_repo: {
            "data": {
                "update": _repo_update_data(
                    auth_repo, event, commits_data, targets_data, error
                ),
                "state": {
                    "transient": transient_data,
                    "persistent": persistent_data,
                },
                "config": get_config(auth_repo.library_dir),
            },
            "commit": commits_data["after_pull"],
        }
    }


def prepare_data_host(
    event,
    transient_data,
    persistent_data,
    library_dir,
    host,
    repos_update_data,
    error,
):
    # combine data about the repos
    host_data_by_repos = {}
    for root_repo, contained_repos_host_data in host.data_by_auth_repo.items():
        auth_repos = []
        for host_auth_repos in contained_repos_host_data["auth_repos"]:
            for repo_name, repo_host_data in host_auth_repos.items():
                repo_data = _repo_update_data(**repos_update_data[repo_name])
                repo_data["custom"] = repo_host_data["custom"]
                auth_repos.append({"update": repo_data})

            host_data_by_repos[root_repo] = {
                "data": {
                    "update": {
                        "changed": event == Event.CHANGED,
                        "event": _format_event(event),
                        "host_name": host.name,
                        "error_msg": str(error) if error else "",
                        "auth_repos": auth_repos,
                        "custom": contained_repos_host_data["custom"],
                    },
                    "state": {
                        "transient": transient_data,
                        "persistent": persistent_data,
                    },
                    "config": get_config(library_dir),
                },
                "commit": repos_update_data[root_repo.name]["commits_data"][
                    "after_pull"
                ],
            }
    return host_data_by_repos


def prepare_data_update(
    event,
    transient_data,
    persistent_data,
    library_dir,
    hosts,
    repos_update_data,
    error,
    root_auth_repo,
):

    update_hosts = {}
    all_auth_repos = {}
    for auth_repo_name in repos_update_data:
        all_auth_repos[auth_repo_name] = _repo_update_data(
            **repos_update_data[auth_repo_name]
        )

    for host_data in hosts:
        auth_repos = {}
        for _, contained_repo_data in host_data.data_by_auth_repo.items():
            for host_auth_repos in contained_repo_data["auth_repos"]:
                for repo_name, repo_host_data in host_auth_repos.items():
                    auth_repo = {}
                    auth_repo[repo_name] = _repo_update_data(
                        **repos_update_data[repo_name]
                    )
                    auth_repo[repo_name]["custom"] = repo_host_data["custom"]
                    auth_repos["update"] = auth_repo

            update_hosts[host_data.name] = {
                "host_name": host_data.name,
                "error_msg": str(error) if error else "",
                "auth_repos": auth_repos,
                "custom": contained_repo_data["custom"],
            }

    return {
        root_auth_repo: {
            "data": {
                "update": {
                    "changed": event == Event.CHANGED,
                    "event": _format_event(event),
                    "error_msg": str(error) if error else "",
                    "hosts": update_hosts,
                    "auth_repos": all_auth_repos,
                    "auth_repo_name": root_auth_repo.name,
                },
                "state": {
                    "transient": transient_data,
                    "persistent": persistent_data,
                },
                "config": get_config(library_dir),
            },
            "commit": repos_update_data[root_auth_repo.name]["commits_data"][
                "after_pull"
            ],
        }
    }


def _repo_update_data(auth_repo, update_status, commits_data, targets_data, error):
    return {
        "changed": update_status == Event.CHANGED,
        "event": _format_event(update_status),
        "repo_name": auth_repo.name,
        "error_msg": str(error) if error else "",
        "auth_repo": {
            "data": auth_repo.to_json_dict(),
            "commits": commits_data,
        },
        "target_repos": targets_data,
    }


def _print_data(repos_and_data, library_dir, lifecycle_stage):
    for repo, data in repos_and_data.items():
        path = Path(library_dir, "data", lifecycle_stage.value, f"{repo.name}.json")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=4))


def _format_event(event):
    if event in (Event.CHANGED, Event.UNCHANGED, Event.SUCCEEDED):
        return f"event/{Event.SUCCEEDED.value}"
    else:
        return f"event/{Event.FAILED.value}"
