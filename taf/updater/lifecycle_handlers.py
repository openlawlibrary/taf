import enum
import glob
import json
from pathlib import Path
from taf.repository_tool import get_target_path
from taf.utils import run


class LifecycleStage(enum.Enum):
    REPO = 1,
    HOST = 2,
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
    LifecycleStage.UPDATE: "update"
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
    Event.COMPLETED: "completed"
}


SCRIPTS_DIR = "scripts"
TRANSIENT_KEY = "transient"
PERSISTENT_KEY = "persistent"


def _get_script_path(lifecycle_stage, event):
    return get_target_path(f"{SCRIPTS_DIR}/{lifecycle_stage.to_name()}/{event.to_name()}")


def handle_repo_event(event, auth_repo, commits, error, targets_pulled_commits, targets_additional_commits):
    _handle_event(LifecycleStage.REPO, event, auth_repo, commits, error,
                  targets_pulled_commits, targets_additional_commits)


def _handle_event(lifecycle_stage, event, *args, **kwargs):
    prepare_data_name = f"prepare_data_{lifecycle_stage.to_name()}"
    data =  globals()[prepare_data_name](*args, **kwargs)


    def _execute_handler(handler, lifecycle_stage, event, data):
        script_rel_path = _get_script_path(lifecycle_stage, event)
        result = handler(script_rel_path, data)
        transient_data = result.get(TRANSIENT_KEY)
        persistent_data = result.get(PERSISTENT_KEY)
        # process transient data
        # process persistent data
        data[PERSISTENT_KEY] = persistent_data
        data[TRANSIENT_KEY] = transient_data

    if event in (Event.CHANGED, Event.UNCHANGED, Event.SUCCEEDED):
        _execute_handler(handle_succeeded, lifecycle_stage, Event.SUCCEEDED, data)
        if event == Event.CHANGED:
            _execute_handler(handle_changed, lifecycle_stage, event, data)
        elif event == Event.UNCHANGED:
            _execute_handler(handle_unchanged, lifecycle_stage, event, data)
    elif event == Event.FAILED:
        _execute_handler(handle_failed, lifecycle_stage, event, data)

    # execute completed handler at the end
    _execute_handler(handle_completed, lifecycle_stage, Event.COMPLETED, data)


def handle_succeeded(script_path, data):
    return {}


def handle_changed(script_path, data):
    return {}


def handle_unchanged(script_path, data):
    return {}


def handle_failed(script_path, data):
    return {}


def handle_completed(script_path, data):
    return {}


def execute_scripts(self, auth_repo, scripts_rel_path, data):
    scripts_path = Path(auth_repo.path, scripts_rel_path)
    scripts = glob.glob(f"{scripts_path}/*.py")
    scripts = [script for script in scripts.sort() if script[0].isdigit()]
    for script in scripts:
        # TODO
        json_data = json.dumps(data)
        output = run("py ", script, "--data ", json_data)

        # transient_data = output.get(TRANSIENT_KEY)
        # persistent_data = output.get(PERSISTENT_KEY)
        # process transient data
        # process persistent data
        # data[PERSISTENT_KEY] = persistent_data
        # data[TRANSIENT_KEY] = transient_data


def prepare_data_repo(auth_repo, commits, targets_data, persistent_data, transient_data):
    return {
        "repo_data": {
            "root_dir": auth_repo.root_dir,
            "name": auth_repo.name,
            "repo_urls": auth_repo.repo_urls,
            "additional_info": auth_repo.additional_info,
            "conf_directory_root": auth_repo.conf_directory_root,
            "hosts": auth_repo.hosts,
        },
        "commits": commits,
        "targets_data": targets_data,
        TRANSIENT_KEY: transient_data,
        PERSISTENT_KEY: persistent_data
    }

def prepare_data_host():
    return {}


def prepare_data_completed():
    return {}
