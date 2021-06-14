import json
import pytest
from jsonschema import validate, RefResolver, Draft7Validator
from jsonschema.exceptions import ValidationError
from pathlib import Path
from taf.updater.schemas import repo_update_schema, host_update_schema


schema_store = {
    repo_update_schema["$id"]: repo_update_schema,
    host_update_schema["$id"]: host_update_schema,
}


def test_repo_validation_valid(repo_handlers_valid_inputs):
    for handler_input_path in repo_handlers_valid_inputs:
        handler_input_data = json.loads(Path(handler_input_path).read_text())
        validate(instance=handler_input_data, schema=repo_update_schema)


def test_host_validation_valid(host_handlers_valid_inputs):
    resolver = RefResolver.from_schema(repo_update_schema, store=schema_store)
    validator = Draft7Validator(host_update_schema, resolver=resolver)

    for handler_input_path in host_handlers_valid_inputs:
        handler_input_data = json.loads(Path(handler_input_path).read_text())
        validator.validate(handler_input_data)


def test_repo_validation_invalid(repo_handlers_invalid_inputs):
    for handler_input_path in repo_handlers_invalid_inputs:
        handler_input_data = json.loads(Path(handler_input_path).read_text())
        with pytest.raises(ValidationError):
            validate(instance=handler_input_data, schema=repo_update_schema)


def test_host_validation_invalid(host_handlers_invalid_inputs):
    resolver = RefResolver.from_schema(repo_update_schema, store=schema_store)
    validator = Draft7Validator(host_update_schema, resolver=resolver)

    for handler_input_path in host_handlers_invalid_inputs:
        handler_input_data = json.loads(Path(handler_input_path).read_text())
        with pytest.raises(ValidationError):
            validator.validate(handler_input_data)
