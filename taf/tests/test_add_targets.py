import json
import os
from pathlib import Path
import pytest
from taf.exceptions import TargetsError

from pytest import fixture

from taf.git import GitRepository


@fixture(autouse=True)
def run_around_tests(repositories):
    yield
    for taf_repository in repositories.values():
        repo = GitRepository(taf_repository.path)
        repo.reset_to_head()
        repo.clean()
        taf_repository._repository.targets.clear_targets()
        files_to_keep = []
        for root, _, filenames in os.walk(str(taf_repository.targets_path)):
            for filename in filenames:
                relpath = Path(root, filename).relative_to(taf_repository.targets_path)
                files_to_keep.append(relpath.as_posix())
        taf_repository.add_targets({}, files_to_keep=files_to_keep)


def test_add_targets_new_files(repositories):
    taf_happy_path = repositories["test-happy-path"]
    old_targets = {"targets": _get_old_targets(taf_happy_path)}

    json_file_content = {"attr1": "value1", "attr2": "value2"}
    regular_file_content = "this file is not empty"
    data = {
        "new_json_file": {"target": json_file_content},
        "new_file": {"target": regular_file_content},
        "empty_file": {"target": None},
    }
    taf_happy_path.add_targets(data)
    _check_target_files(taf_happy_path, data, old_targets)


def test_add_targets_nested_files(repositories):
    taf_happy_path = repositories["test-happy-path"]
    old_targets = {"targets": _get_old_targets(taf_happy_path)}

    data = {
        "inner_folder1/new_file_1": {"target": "file 1 content"},
        "inner_folder2/new_file_2": {"target": "file 2 content"},
    }
    taf_happy_path.add_targets(data)
    _check_target_files(taf_happy_path, data, old_targets)


def test_add_targets_files_to_keep(repositories):
    taf_happy_path = repositories["test-happy-path"]
    old_targets = {"targets": _get_old_targets(taf_happy_path)}
    data = {"a_new_file": {"target": "new file content"}}
    files_to_keep = ["branch"]
    taf_happy_path.add_targets(data, files_to_keep=files_to_keep)
    _check_target_files(taf_happy_path, data, old_targets, files_to_keep=files_to_keep)


def test_add_targets_delegated_roles_no_child_roles(repositories):
    taf_delegated_roles = repositories["test-delegated-roles"]
    old_targets = {
        "delegated_role1": ["dir1/delegated_role1_1.txt", "dir1/delegated_role1_2.txt"],
        "delegated_role2": ["dir2/delegated_role2_1.txt", "dir2/delegated_role2_2.txt"],
        "inner_delegated_role": ["dir2/inner_delegated_role.txt"],
    }

    data = {"dir1/a_new_file": {"target": "new file content"}}
    with pytest.raises(TargetsError):
        taf_delegated_roles.add_targets(data, targets_role="delegated_role2")
    role = "delegated_role1"
    taf_delegated_roles.add_targets(data, targets_role=role)
    _check_target_files(taf_delegated_roles, data, old_targets, role)


def test_add_targets_delegated_roles_child_roles(repositories):
    taf_delegated_roles = repositories["test-delegated-roles"]
    old_targets = {
        "delegated_role1": ["dir1/delegated_role1_1.txt", "dir1/delegated_role1_2.txt"],
        "delegated_role2": ["dir2/delegated_role2_1.txt", "dir2/delegated_role2_2.txt"],
        "inner_delegated_role": ["dir2/inner_delegated_role.txt"],
    }

    data = {"dir2/a_new_file": {"target": "new file content"}}
    with pytest.raises(TargetsError):
        taf_delegated_roles.add_targets(data, targets_role="delegated_role1")
    role = "delegated_role2"
    taf_delegated_roles.add_targets(data, targets_role=role)
    _check_target_files(taf_delegated_roles, data, old_targets, role)


def _check_target_files(
    repo, data, old_targets, targets_role="targets", files_to_keep=None
):
    if files_to_keep is None:
        files_to_keep = []

    targets_path = repo.targets_path
    for target_rel_path, content in data.items():
        target_path = targets_path / target_rel_path
        assert target_path.exists()
        with open(str(target_path)) as f:
            file_content = f.read()
            target_content = content["target"]
            if isinstance(target_content, dict):
                content_json = json.loads(file_content)
                assert content_json == target_content
            elif target_content:
                assert file_content == target_content
            else:
                assert file_content == ""

    # make sure that everything defined in repositories.json still exists if there was
    # repositories.json
    repository_targets = []
    for _, roles_targets in old_targets.items():
        if "repositories.json" in roles_targets:
            repositories_path = targets_path / "repositories.json"
            assert repositories_path.exists()
            with open(str(repositories_path)) as f:
                repositories = json.load(f)["repositories"]
                for target_rel_path in repositories:
                    target_path = targets_path / target_rel_path
                    assert target_path.exists()
                    repository_targets.append(target_rel_path)
            break

    # make sure that files to keep exist
    for file_to_keep in files_to_keep:
        # if the file didn't exists prior to adding new targets
        # it won't exists after adding them
        if file_to_keep not in old_targets:
            continue
        target_path = targets_path / file_to_keep
        assert target_path.exists()

    for role, old_roles_target in old_targets.items():
        for old_target in old_roles_target:
            if role != targets_role:
                assert (targets_path / old_target).exists() is True
            elif (
                old_target not in repository_targets
                and old_target not in data
                and old_target not in repo._framework_files
                and old_target not in files_to_keep
            ):
                assert (targets_path / old_target).exists() is False


def _get_old_targets(repo):
    targets_path = repo.targets_path
    old_targets = []
    for root, _, filenames in os.walk(str(targets_path)):
        for filename in filenames:
            rel_path = Path(root, filename).relative_to(targets_path)
            old_targets.append(rel_path.as_posix())
    return old_targets
