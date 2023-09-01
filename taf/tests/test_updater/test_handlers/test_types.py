import json
from taf.updater.types.update import Update
from pathlib import Path
from cattr import structure


def test_update_structure_valid(types_update_valid_inputs):
    for handler_input_path in types_update_valid_inputs:
        handler_input_data = json.loads(Path(handler_input_path).read_text())
        result = structure(handler_input_data, Update)
        assert (
            Update(
                changed=result.changed,
                error_msg=result.error_msg,
                event=result.event,
                auth_repos=result.auth_repos,
                auth_repo_name="openlawlibrary/law",
            )
            == result
        )


def test_update_structure_invalid(types_update_invalid_inputs):
    for handler_input_path in types_update_invalid_inputs:
        handler_input_data = json.loads(Path(handler_input_path).read_text())
        result = structure(handler_input_data, Update)
        assert (
            Update(
                changed=False,
                event="",
                error_msg="",
                auth_repos={},
                auth_repo_name="",
            )
            == result
        )
