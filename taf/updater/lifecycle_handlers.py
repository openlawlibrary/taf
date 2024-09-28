import attr
import enum
import glob
import json
import subprocess
import sys
from functools import partial
from pathlib import Path

import taf.settings as settings
from taf.repository_tool import get_target_path
from taf.utils import (
    run,
    safely_save_json_to_disk,
    extract_json_objects_from_trusted_stdout,
    run_subprocess,
)
from taf.exceptions import GitError, ScriptExecutionError
from taf.log import taf_logger
from taf.updater.types.update import Update
from cattr import structure


class LifecycleStage(enum.Enum):
    REPO = "repo"
    UPDATE = "update"


class Event(enum.Enum):
    SUCCEEDED = "succeeded"
    CHANGED = "changed"
    UNCHANGED = "unchanged"
    FAILED = "failed"
    PARTIAL = "partial"
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
        config_path = Path(library_root, CONFIG_NAME)
        try:
            config = json.loads(Path(config_path).read_text())
        except Exception:
            config = {}
            taf_logger.info(
                f"WARNING: Config file {config_path} not found. Scripts might not be executed successfully"
            )
        config_db[library_root] = config or {}
    return config_db.get(library_root)


def get_persistent_data(library_root, persistent_file=PERSISTENT_FILE_NAME):
    if not Path(library_root).is_dir():
        return {}
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
            # there is no reason to try executing the scripts if last_commit is None
            # that means that update was not even starterd
            if last_commit is not None:
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
        script_paths = glob.glob(f"{path}/*")
    else:
        try:
            script_names = auth_repo.list_files_at_revision(
                last_commit, scripts_rel_path
            )
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
        except GitError:
            taf_logger.debug(f"{scripts_rel_path} does not contain any scripts")
            script_paths = []

    for script_path in sorted(script_paths):
        taf_logger.log("NOTICE", f"Executing script {script_path}")
        json_data = json.dumps(data)
        try:
            if Path(script_path).suffix == ".py":
                if getattr(sys, "frozen", False):
                    # we are running in a pyinstaller bundle
                    output = run(
                        f"{sys.executable}",
                        "scripts",
                        "execute",
                        script_path,
                        input=json_data,
                    )
                else:
                    output = run(f"{sys.executable}", script_path, input=json_data)
            # assume that all other types of files are non-OS-specific executables of some kind
            else:
                output = run_subprocess([script_path])
        except Exception as e:
            if type(e) is subprocess.CalledProcessError:
                taf_logger.error(
                    f"An error occurred while executing {script_path}: {e.output}"
                )
                raise ScriptExecutionError(script_path, e.output)
            else:
                taf_logger.error(
                    f"An error occurred while executing {script_path}: {str(e)}"
                )
                raise ScriptExecutionError(script_path, str(e))
        if type(output) is bytes:
            output = output.decode()
        transient_data = persistent_data = {}
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
    return auth_repo, commits_data.after_pull


def get_script_repo_and_commit_update(auth_repo, commits_data, *args):
    pass


def prepare_data_repo(
    event,
    transient_data,
    persistent_data,
    library_dir,
    auth_repo,
    commits_data,
    error,
    warnings,
    targets_data,
):
    conf_data = get_config(auth_repo.library_dir)
    if not conf_data:
        taf_logger.debug(
            f"WARNING: No config data at {Path(library_dir, CONFIG_NAME)}. Scripts might not be executed successfully"
        )
    return {
        auth_repo: {
            "data": {
                "update": _repo_update_data(
                    auth_repo, event, commits_data, targets_data, error, warnings
                ),
                "state": {
                    "transient": transient_data,
                    "persistent": persistent_data,
                },
                "config": conf_data,
            },
            "commit": commits_data.after_pull,
        }
    }


def prepare_data_update(
    event,
    transient_data,
    persistent_data,
    library_dir,
    repos_update_data,
    error,
    root_auth_repo,
):

    all_auth_repos = {}
    for auth_repo_name in repos_update_data:
        all_auth_repos[auth_repo_name] = _repo_update_data(
            **repos_update_data[auth_repo_name]
        )

    return {
        root_auth_repo: {
            "data": {
                "update": {
                    "changed": event == Event.CHANGED,
                    "event": _format_event(event),
                    "error_msg": str(error) if error else "",
                    "auth_repos": all_auth_repos,
                    "auth_repo_name": root_auth_repo.name,
                },
                "state": {
                    "transient": transient_data,
                    "persistent": persistent_data,
                },
                "config": get_config(library_dir),
            },
            "commit": repos_update_data[root_auth_repo.name]["commits_data"].after_pull,
        }
    }


def _repo_update_data(
    auth_repo, update_status, commits_data, targets_data, error, warnings
):
    return {
        "changed": update_status == Event.CHANGED,
        "event": _format_event(update_status),
        "repo_name": auth_repo.name,
        "error_msg": str(error) if error else "",
        "warnings": warnings or "",
        "auth_repo": {
            "data": auth_repo.to_json_dict(),
            "commits": attr.asdict(commits_data),
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
