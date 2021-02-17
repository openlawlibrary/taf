import enum
import glob
import json
from pathlib import Path

import taf.settings as settings
from taf.repository_tool import get_target_path
from taf.utils import run, safely_save_json_to_disk


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
TRANSIENT_KEY = "transient"
PERSISTENT_KEY = "persistent"
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
            config_db[library_root] = config
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
        persistent_data_db[library_root] = data
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
        auth_repo,
        commits_data,
        error,
        targets_data,
    )


def _handle_event(
    lifecycle_stage, event, transient_data, auth_repo, commits_data, *args, **kwargs
):
    # read initial persistent data from file
    persistent_data = get_persistent_data(auth_repo.root_dir)
    prepare_data_name = f"prepare_data_{lifecycle_stage.to_name()}"
    data = globals()[prepare_data_name](
        event, persistent_data, transient_data, auth_repo, commits_data, *args, **kwargs
    )

    def _execute_scripts(auth_repo, lifecycle_stage, event, data):
        last_commit = commits_data["after_pull"]
        scripts_rel_path = _get_script_path(lifecycle_stage, event)
        result = execute_scripts(auth_repo, last_commit, scripts_rel_path, data)


    if event in (Event.CHANGED, Event.UNCHANGED, Event.SUCCEEDED):
        # if event is changed or unchanged, execute these scripts first, then call the succeeded script
        if event == Event.CHANGED:
            _execute_scripts(auth_repo, lifecycle_stage, event, data)
        elif event == Event.UNCHANGED:
            _execute_scripts(auth_repo, lifecycle_stage, event, data)
        _execute_scripts(auth_repo, lifecycle_stage, Event.SUCCEEDED, data)
    elif event == Event.FAILED:
        _execute_scripts(auth_repo, lifecycle_stage, event, data)

    # execute completed handler at the end
    _execute_scripts(auth_repo, lifecycle_stage, Event.COMPLETED, data)


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
        script_rel_paths = [Path(scripts_rel_path, script_name).as_posix() for script_name in script_names if Path(script_name).suffix == ".py"]
        # need to check if the path ends with py
        auth_repo.checkout_paths(last_commit, *script_rel_paths)
        script_paths = [str(Path(auth_repo.path, script_rel_path)) for script_rel_path in script_rel_paths]

    for script_path in sorted(script_paths):
        # TODO
        # each script need to return persistent and transient data and that data needs to be passed into the next script
        # other data should stay the same
        # this function needs to return the transient and persistent data returned by the last script
        json_data = json.dumps(data)
        output = run("py", script_path, input=json_data)
        if output is not None and output != "":
            output = json.loads(output)
            transient_data = output.get(TRANSIENT_KEY)
            persistent_data = output.get(PERSISTENT_KEY)
            if transient_data is not None:
                data[TRANSIENT_KEY].update(transient_data)
            if persistent_data is not None:
                data[PERSISTENT_KEY].update(persistent_data)
            import pdb; pdb.set_trace
            safely_save_json_to_disk(data[PERSISTENT_KEY], persistent_path)
    return data[TRANSIENT_KEY], data[PERSISTENT_KEY]


def prepare_data_repo(
    event,
    transient_data,
    persistent_data,
    auth_repo,
    commits_data,
    error,
    targets_data,
):
    if transient_data is None:
        transient_data = {}
    if persistent_data is None:
        persistent_data = {}
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
            "target_repos": targets_data
        },
        "state": {
            TRANSIENT_KEY: transient_data,
            PERSISTENT_KEY: persistent_data,
        },
        "config": get_config(auth_repo.root_dir)
    }


def prepare_data_host():
    return {}


def prepare_data_completed():
    return {}
