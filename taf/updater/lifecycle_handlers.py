import enum
import glob
import json
import subprocess
from pathlib import Path

import taf.settings as settings
from taf.repository_tool import get_target_path
from taf.utils import run, safely_save_json_to_disk
from taf.exceptions import ScriptExecutionError


class LifecycleStage(enum.Enum):
    REPO = (1,)
    HOST = (2,)
    UPDATE = 3

    @classmethod
    def from_name(cls, name):
        stage = {v: k for k, v in LIFECYCLE_NAMES.items()}.get(name)
        if stage is not None:
            return stage
        raise ValueError(f"{name} is not a valid lifecycle stage")

    def to_name(self):
        return LIFECYCLE_NAMES[self]


LIFECYCLE_NAMES = {
    LifecycleStage.REPO: "repo",
    LifecycleStage.HOST: "host",
    LifecycleStage.UPDATE: "update",
}


class Event(enum.Enum):
    SUCCEEDED = 1
    CHANGED = 2
    UNCHANGED = 3
    FAILED = 4
    COMPLETED = 5

    @classmethod
    def from_name(cls, name):
        event = {v: k for k, v in EVENT_NAMES.items()}.get(name)
        if event is not None:
            return event
        raise ValueError(f"{name} is not a valid event")

    def to_name(self):
        return EVENT_NAMES[self]


EVENT_NAMES = {
    Event.SUCCEEDED: "succeeded",
    Event.CHANGED: "changed",
    Event.UNCHANGED: "unchanged",
    Event.FAILED: "failed",
    Event.COMPLETED: "completed",
}


CONFIG_NAME = "config.json"
SCRIPTS_DIR = "scripts"
PERSISTENT_FILE_NAME = "persistent.json"


# config should only be read once per library root
# make it flexible in case the updater needs to handle libraries with different roots
config_db = {}


# persistent data should be read from persistent file and updated after every handler call
# should be one file per library root
persistent_data_db = {}


def _get_script_path(lifecycle_stage, event):
    return get_target_path(
        f"{SCRIPTS_DIR}/{lifecycle_stage.to_name()}/{event.to_name()}"
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
    global persistent_data_db
    persistent_file = Path(library_root, PERSISTENT_FILE_NAME)
    if not persistent_file.is_file():
        persistent_file.touch()

    if library_root not in persistent_data_db:
        try:
            data = json.loads(persistent_file.read_text())
        except Exception:
            data = {}
        persistent_data_db[library_root] = data or {}
    return persistent_data_db.get(library_root)


def handle_repo_event(
    event,
    auth_repo,
    commits_data,
    error,
    targets_data,
    transient_data=None,
):
    _handle_event(
        LifecycleStage.REPO,
        event,
        transient_data,
        auth_repo.root_dir,
        auth_repo,
        commits_data,
        error,
        targets_data,
    )

def handle_host_event():
    pass


def _handle_event(
    lifecycle_stage, event, transient_data, root_dir, *args, **kwargs
):
    # read initial persistent data from file
    persistent_data = get_persistent_data(root_dir)
    transient_data = transient_data or {}
    prepare_data_name = f"prepare_data_{lifecycle_stage.to_name()}"
    data = globals()[prepare_data_name](
        event, transient_data, persistent_data, *args, **kwargs
    )
    script_repo_and_commit_name = f"get_script_repo_and_commit_{lifecycle_stage.to_name()}"
    auth_repo, last_commit = globals()[script_repo_and_commit_name](
        *args, **kwargs
    )

    def _execute_scripts(auth_repo, last_commit, lifecycle_stage, event, data):
        scripts_rel_path = _get_script_path(lifecycle_stage, event)
        # this will update data
        return execute_scripts(auth_repo, last_commit, scripts_rel_path, data)

    if event in (Event.CHANGED, Event.UNCHANGED, Event.SUCCEEDED):
        # if event is changed or unchanged, execute these scripts first, then call the succeeded script
        if event == Event.CHANGED:
            data = _execute_scripts(auth_repo, last_commit, lifecycle_stage, event, data)
        elif event == Event.UNCHANGED:
            data = _execute_scripts(auth_repo, last_commit, lifecycle_stage, event, data)
        data = _execute_scripts(auth_repo, last_commit, lifecycle_stage, Event.SUCCEEDED, data)
    elif event == Event.FAILED:
        data = _execute_scripts(auth_repo, last_commit, lifecycle_stage, event, data)

    # execute completed handler at the end
    data = _execute_scripts(auth_repo, last_commit, lifecycle_stage, Event.COMPLETED, data)

    # return transient data as it should be propagated to other events and handlers
    return data["state"]["transient"]


def execute_scripts(auth_repo, last_commit, scripts_rel_path, data):
    persistent_path = Path(auth_repo.root_dir, PERSISTENT_FILE_NAME)
    # do not load the script from the file system
    # the update might have failed because the repository contains an additional
    # commit with, say, malicious scripts
    # load the scripts from the last validated commit - whether new or old

    # this is a nightmare to test
    # load from filesystem in development mode so that the scripts can be updated without
    # having to commit and push
    development_mode = settings.development_mode

    if development_mode:
        path = str(Path(auth_repo.path, scripts_rel_path))
        script_paths = glob.glob(f"{path}/*.py")
    else:
        script_names = auth_repo.list_files_at_revision(last_commit, scripts_rel_path)
        script_rel_paths = [
            Path(scripts_rel_path, script_name).as_posix()
            for script_name in script_names
            if Path(script_name).suffix == ".py"
        ]
        # need to check if the path ends with py
        auth_repo.checkout_paths(last_commit, *script_rel_paths)
        script_paths = [
            str(Path(auth_repo.path, script_rel_path))
            for script_rel_path in script_rel_paths
        ]

    for script_path in sorted(script_paths):
        # TODO
        # each script need to return persistent and transient data and that data needs to be passed into the next script
        # other data should stay the same
        # this function needs to return the transient and persistent data returned by the last script
        json_data = json.dumps(data)
        try:
            output = run("py", script_path, input=json_data)
        except subprocess.CalledProcessError as e:
            raise ScriptExecutionError(script_path, e.output)
        if output is not None and output != "":
            output = json.loads(output)
            transient_data = output.get("transient")
            persistent_data = output.get("persistent")
        else:
            transient_data = persistent_data = {}
        print(persistent_data)

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


def get_script_repo_and_commit_repo(
    auth_repo,
    commits_data,
    *args
):
    return auth_repo, commits_data["after_pull"]


def get_script_repo_and_commit_host(
    auth_repo,
    commits_data,
    *args
):
    pass


def prepare_data_repo(
    event,
    transient_data,
    persistent_data,
    auth_repo,
    commits_data,
    error,
    targets_data,
):
    # commits should be a dictionary containing new commits,
    # commit before pull and commit after pull
    # commit before pull is not equal to the first new commit
    # if the repository was freshly cloned
    if event in (Event.CHANGED, Event.UNCHANGED, Event.SUCCEEDED):
        event = f"event/{Event.SUCCEEDED.to_name()}"
    else:
        event = f"event/{Event.FAILED.to_name()}"
    return {
        "update": {
            "changed": event == Event.CHANGED,
            "event": event,
            "repo_name": auth_repo.name,
            "error_msg": str(error) if error else "",
            "auth_repo": {
                "data": auth_repo.to_json_dict(),
                "commits": commits_data,
            },
            "target_repos": targets_data,
        },
        "state": {
            "transient": transient_data,
            "persistent": persistent_data,
        },
        "config": get_config(auth_repo.root_dir),
    }


def prepare_data_host():
    return {}


def prepare_data_completed():
    return {}
