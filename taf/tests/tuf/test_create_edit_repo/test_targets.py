from collections import defaultdict


def test_add_target_files(tuf_repo):

    # assert add target file and correct version bumps
    path1 = "test1"
    tuf_repo.add_target_files_to_role({path1: {"target": "test1"}})
    assert (tuf_repo.path / "targets" / path1).is_file()
    assert tuf_repo.targets().targets[path1]
    assert tuf_repo.targets().targets[path1].length > 0
    assert len(tuf_repo.targets().targets[path1].hashes) == 2
    assert tuf_repo.root().version == 1
    assert tuf_repo.timestamp().version == 1
    assert tuf_repo.snapshot().version == 1
    assert tuf_repo.targets().version == 2

    # now add with custom
    path2 = "test2"
    custom = {"custom_attr": "custom_val"}
    tuf_repo.add_target_files_to_role({path2: {"target": "test2", "custom": custom}})
    assert (tuf_repo.path / "targets" / path2).is_file()
    assert tuf_repo.targets().targets[path2].length > 0
    assert tuf_repo.targets().targets[path2].custom == custom


def test_repo_target_files(tuf_repo):
    # assert add target file and correct version bumps
    path1 = "test1"
    path2 = "test2"
    tuf_repo.add_target_files_to_role(
        {path1: {"target": "test1"}, path2: {"target": "test2"}}
    )
    for path in (path1, path2):
        assert (tuf_repo.path / "targets" / path).is_file()
        assert tuf_repo.targets().targets[path].length > 0

    tuf_repo.modify_targets(added_data=None, removed_data={path1: None})
    assert not (tuf_repo.path / "targets" / path1).is_file()
    assert (tuf_repo.path / "targets" / path2).is_file()
    assert path1 not in tuf_repo.targets().targets
    assert path2 in tuf_repo.targets().targets


def test_repo_target_files_with_delegations(tuf_repo):

    target_path1 = "test1"
    target_path2 = "test2"

    tuf_repo.add_target_files_to_role(
        {target_path1: {"target": "test1"}, target_path2: {"target": "test2"}}
    )
    for path in (target_path1, target_path2):
        assert (tuf_repo.path / "targets" / path).is_file()
        assert tuf_repo.targets().targets[path].length > 0

    delegated_path1 = "dir1/path1"
    delegated_path2 = "dir2/path1"

    tuf_repo.add_target_files_to_role(
        {delegated_path1: {"target": "test1"}, delegated_path2: {"target": "test2"}}
    )
    for path in (delegated_path1, delegated_path2):
        assert (tuf_repo.path / "targets" / path).is_file()
        assert tuf_repo._signed_obj("delegated_role").targets[path].length > 0

    path_delegated = "dir2/path2"
    tuf_repo.add_target_files_to_role(
        {
            path_delegated: {"target": "test3"},
        }
    )
    assert tuf_repo._signed_obj("inner_role").targets[path_delegated].length > 0


def test_get_all_target_files_state(tuf_repo):

    # assert add target file and correct version bumps

    target_path1 = "test1"
    target_path2 = "test2"

    tuf_repo.add_target_files_to_role(
        {target_path1: {"target": "test1"}, target_path2: {"target": "test2"}}
    )

    (tuf_repo.path / "targets" / target_path1).unlink()

    delegated_path1 = "dir1/path1"
    delegated_path2 = "dir2/path1"

    tuf_repo.add_target_files_to_role(
        {delegated_path1: {"target": "test1"}, delegated_path2: {"target": "test2"}}
    )
    path = tuf_repo.path / "targets" / delegated_path1
    path.write_text("Updated content")

    actual = tuf_repo.get_all_target_files_state()
    assert actual == (
        {delegated_path1: {"target": "Updated content"}},
        {target_path1: {}},
    )


def test_delete_unregistered_target_files(tuf_repo):

    # assert add target file and correct version bumps
    tuf_repo.add_target_files_to_role(
        {"test1": {"target": "test1"}, "test2": {"target": "test2"}}
    )

    tuf_repo.add_target_files_to_role(
        {"dir1/path1": {"target": "test1"}, "dir2/path1": {"target": "test2"}}
    )
    new_target1 = tuf_repo.path / "targets" / "new"
    new_target1.touch()
    new_target2 = tuf_repo.path / "targets" / "dir1" / "new"
    new_target2.touch()
    assert new_target1.is_file()
    assert new_target2.is_file()
    tuf_repo.delete_unregistered_target_files()
    assert not new_target1.is_file()
    tuf_repo.delete_unregistered_target_files("delegated_role")
    assert not new_target2.is_file()


def test_update_target_toles(tuf_repo):
    # create files on disk and then update the roles
    # check if the metadata files were updated successfully

    targets_dir = tuf_repo.path / "targets"
    dir1 = targets_dir / "dir1"
    dir1.mkdir(parents=True)

    new_target1 = targets_dir / "new1"
    new_target1.write_text(
        "This file is not empty and its lenght should be greater than 0"
    )
    new_target2 = dir1 / "new2"
    new_target2.touch()
    new_target3 = dir1 / "new3"
    new_target3.write_text("This file also contains something")

    added_targets_data, removed_targets_data = tuf_repo.get_all_target_files_state()
    assert len(added_targets_data) == 3
    assert len(removed_targets_data) == 0

    roles_and_targets = defaultdict(list)
    for path in added_targets_data:
        roles_and_targets[tuf_repo.get_role_from_target_paths([path])].append(path)

    len(roles_and_targets) == 2
    assert len(roles_and_targets["targets"]) == 1
    assert len(roles_and_targets["delegated_role"]) == 2

    tuf_repo.update_target_role("targets", roles_and_targets["targets"])
    targets_obj = tuf_repo._signed_obj("targets")
    assert targets_obj.targets
    assert len(targets_obj.targets) == 1
    target_name = "new1"
    assert target_name in targets_obj.targets
    assert targets_obj.targets[target_name].length > 0
    assert (
        "sha256" in targets_obj.targets[target_name].hashes
        and "sha512" in targets_obj.targets[target_name].hashes
    )

    tuf_repo.update_target_role("delegated_role", roles_and_targets["delegated_role"])
    targets_obj = tuf_repo._signed_obj("delegated_role")
    assert targets_obj.targets
    assert len(targets_obj.targets) == 2
    target_name = "dir1/new2"
    assert target_name in targets_obj.targets
    assert targets_obj.targets[target_name].length == 0
    assert (
        "sha256" in targets_obj.targets[target_name].hashes
        and "sha512" in targets_obj.targets[target_name].hashes
    )
    target_name = "dir1/new3"
    assert target_name in targets_obj.targets
    assert targets_obj.targets[target_name].length > 0
    assert (
        "sha256" in targets_obj.targets[target_name].hashes
        and "sha512" in targets_obj.targets[target_name].hashes
    )
