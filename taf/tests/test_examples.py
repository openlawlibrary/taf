import doctest
import importlib
import json
import re
from pathlib import Path

import pytest

import taf
from taf.api.roles import _transform_roles_dict
from taf.models.converter import from_dict
from taf.models.types import RolesKeysData
from taf.tools.keystore import generate_keys_command
from taf.tools.repo import create_repo_command
from taf.tools.roles import add_roles_command

TAF_DIR = Path(taf.__file__).parent
OPTION_FLAGS = doctest.ELLIPSIS | doctest.NORMALIZE_WHITESPACE


def _modules_with_doctests():
    """Names of all taf modules (tests excluded) that contain a doctest
    example. Found by reading the files, so that nothing is imported while
    the tests are being collected."""
    module_names = []
    for path in sorted(TAF_DIR.rglob("*.py")):
        relative_path = path.relative_to(TAF_DIR)
        if relative_path.parts[0] == "tests":
            continue
        if ">>> " not in path.read_text(encoding="utf-8"):
            continue
        parts = list(relative_path.with_suffix("").parts)
        if parts[-1] == "__init__":
            parts.pop()
        module_names.append(".".join(["taf", *parts]))
    return module_names


@pytest.mark.parametrize("module_name", _modules_with_doctests())
def test_doctests(module_name):
    """Run the examples written in the docstrings of a module, so that they
    cannot fall behind the code that they describe."""
    module = importlib.import_module(module_name)
    results = doctest.testmod(module, optionflags=OPTION_FLAGS)
    assert results.attempted > 0, f"No doctest examples were run in {module_name}"
    assert results.failed == 0, f"{results.failed} doctest example(s) failed"


DOCS_DIR = TAF_DIR.parent / "docs"
CODE_BLOCK = re.compile(r"```\w*\n(.*?)```", re.DOTALL)


def _docs_keys_description_examples():
    """Keys description examples found in the markdown docs, as
    (file name and position, text of the example) pairs."""
    examples = []
    for path in sorted(DOCS_DIR.rglob("*.md")):
        blocks = CODE_BLOCK.findall(path.read_text(encoding="utf-8"))
        for position, block in enumerate(blocks):
            if '"roles"' in block:
                examples.append(
                    pytest.param(block, id=f"{path.relative_to(DOCS_DIR)}-{position}")
                )
    return examples


@pytest.mark.parametrize("example", _docs_keys_description_examples())
def test_docs_keys_description_examples(example, tmp_path):
    """Keys description examples in the docs have to be valid. The keystore
    directory has to exist, so the example's keystore path is replaced by an
    existing one."""
    keys_description = json.loads(example)
    if "keystore" in keys_description:
        keys_description["keystore"] = str(tmp_path)
    assert isinstance(from_dict(keys_description, RolesKeysData), RolesKeysData)


def _json_example_from_help(command):
    """The JSON example shown in the help text of a command, as a dictionary."""
    start = command.help.index("{")
    example, _ = json.JSONDecoder().raw_decode(command.help[start:])
    return example


@pytest.mark.parametrize(
    "command_factory", [create_repo_command, generate_keys_command]
)
def test_help_keys_description_examples(command_factory, tmp_path):
    """Keys description examples shown in the help of the commands have to
    be valid. The keystore directory has to exist, so the example's keystore
    path is replaced by an existing one."""
    keys_description = _json_example_from_help(command_factory())
    keys_description["keystore"] = str(tmp_path)
    roles_keys_data = from_dict(keys_description, RolesKeysData)
    root = roles_keys_data.roles.root
    assert (root.number, root.threshold, root.length) == (3, 2, 2048)
    assert roles_keys_data.roles.targets.length == 2048


def test_help_add_roles_example():
    """The example shown in the help of the command which adds multiple
    roles has to be valid. It is read the same way as when the command is run."""
    example = _json_example_from_help(add_roles_command())
    roles_keys_data = from_dict(
        _transform_roles_dict(example, key_names=[]), RolesKeysData
    )
    assert sorted(roles_keys_data.yubikeys) == ["user1", "userYK"]
    new_role = roles_keys_data.roles.targets.delegations["delegated_role"]
    assert new_role.parent.name == "targets"
    assert new_role.paths == [
        "delegated_path_inside_targets1/*",
        "delegated_path_inside_targets2/*",
    ]
    assert (new_role.number, new_role.threshold) == (2, 1)
    assert new_role.yubikeys == ["user1", "userYK"]
