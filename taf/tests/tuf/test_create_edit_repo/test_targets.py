


from taf.models.converter import from_dict
from taf.models.types import RolesKeysData
from taf.tuf.repository import MetadataRepository, TargetFile


def test_add_target_files(repo_path, signers, no_yubikeys_input):
    # Create new metadata repository
    tuf_repo = MetadataRepository(repo_path)
    roles_keys_data = from_dict(no_yubikeys_input, RolesKeysData)
    tuf_repo.create(roles_keys_data, signers)

    # assert add target file and correct version bumps
    path1 = "test1.txt"
    tuf_repo.add_target_files_to_role({path1: {"target": "test1"}})
    assert (tuf_repo._path / "targets" / path1).is_file()
    assert tuf_repo.targets().targets[path1]
    assert tuf_repo.targets().targets[path1].length > 0
    assert len(tuf_repo.targets().targets[path1].hashes) == 2
    assert tuf_repo.root().version == 1
    assert tuf_repo.timestamp().version == 2
    assert tuf_repo.snapshot().version == 2
    assert tuf_repo.targets().version == 2
    assert tuf_repo.timestamp().snapshot_meta.version == 2
    assert tuf_repo.snapshot().meta["root.json"].version == 1
    assert tuf_repo.snapshot().meta["targets.json"].version == 2

    # now add with custom
    path2 = "test2.txt"
    custom =  {"custom_attr": "custom_val"}
    tuf_repo.add_target_files_to_role({path2: {"target": "test2", "custom": custom}})
    assert (tuf_repo._path / "targets" / path2).is_file()
    assert tuf_repo.targets().targets[path2].length > 0
    assert tuf_repo.targets().targets[path2].custom ==  custom


def test_repo_target_files(repo_path, signers, no_yubikeys_input):
    # Create new metadata repository
    tuf_repo = MetadataRepository(repo_path)
    roles_keys_data = from_dict(no_yubikeys_input, RolesKeysData)
    tuf_repo.create(roles_keys_data, signers)

    # assert add target file and correct version bumps
    path1 = "test1.txt"
    path2 = "test2.txt"
    tuf_repo.add_target_files_to_role({
        path1: {"target": "test1"},
        path2: {"target": "test2"}
        }
    )
    for path in (path1, path2):
        assert (tuf_repo._path / "targets" / path).is_file()
        assert tuf_repo.targets().targets[path].length > 0

    tuf_repo.modify_targets(added_data=None, removed_data={path1: None})
    assert not (tuf_repo._path / "targets" / path1).is_file()
    assert (tuf_repo._path / "targets" / path2).is_file()
    assert path1 not in tuf_repo.targets().targets
    assert path2 in tuf_repo.targets().targets


def test_repo_target_files_with_delegations(repo_path, signers_with_delegations, with_delegations_no_yubikeys_input):
    # Create new metadata repository
    tuf_repo = MetadataRepository(repo_path)
    roles_keys_data = from_dict(with_delegations_no_yubikeys_input, RolesKeysData)
    tuf_repo.create(roles_keys_data, signers_with_delegations)

    # assert add target file and correct version bumps

    target_path1 = "test1"
    target_path2 = "test2"

    tuf_repo.add_target_files_to_role({
        target_path1: {"target": "test1"},
        target_path2: {"target": "test2"}
        }
    )
    for path in (target_path1, target_path2):
        assert (tuf_repo._path / "targets" / path).is_file()
        assert tuf_repo.targets().targets[path].length > 0

    delegated_path1 = "dir1/path1"
    delegated_path2 = "dir2/path1"

    tuf_repo.add_target_files_to_role({
        delegated_path1: {"target": "test1"},
        delegated_path2: {"target": "test2"}
        }
    )
    for path in (delegated_path1, delegated_path2):
        assert (tuf_repo._path / "targets" / path).is_file()
        assert tuf_repo._signed_obj("delegated_role").targets[path].length > 0

    path_delegated = "dir2/path2"
    tuf_repo.add_target_files_to_role({
        path_delegated: {"target": "test3"},
        }
    )
    assert tuf_repo._signed_obj("inner_role").targets[path_delegated].length > 0


def test_get_all_target_files_state(repo_path, signers_with_delegations, with_delegations_no_yubikeys_input):

    tuf_repo = MetadataRepository(repo_path)
    roles_keys_data = from_dict(with_delegations_no_yubikeys_input, RolesKeysData)
    tuf_repo.create(roles_keys_data, signers_with_delegations)

    # assert add target file and correct version bumps

    target_path1 = "test1"
    target_path2 = "test2"

    tuf_repo.add_target_files_to_role({
        target_path1: {"target": "test1"},
        target_path2: {"target": "test2"}
        }
    )

    (tuf_repo._path / "targets" / target_path1).unlink()

    delegated_path1 = "dir1/path1"
    delegated_path2 = "dir2/path1"

    tuf_repo.add_target_files_to_role({
        delegated_path1: {"target": "test1"},
        delegated_path2: {"target": "test2"}
        }
    )
    path = tuf_repo._path / "targets" / delegated_path1
    path.write_text("Updated content")

    actual = tuf_repo.get_all_target_files_state()
    assert actual == ({delegated_path1: {'target': 'Updated content', 'custom': None}}, {target_path1: {}})

# def test_add_keys(self, tmp_path, test_signers, test_signer2):
#     repo = MetadataRepository(tmp_path)
#     repo.create(test_signers)

#     # assert add new root key and version bumps (all but targets)
#     repo.add_keys([test_signer2], "root")
#     assert test_signer2.public_key.keyid in repo.root().keys
#     assert test_signer2.public_key.keyid in repo.root().roles["root"].keyids
#     assert repo.root().version == 2
#     assert repo.timestamp().version == 2
#     assert repo.snapshot().version == 2
#     assert repo.targets().version == 1
#     assert repo.timestamp().snapshot_meta.version == 2
#     assert repo.snapshot().meta["root.json"].version == 2
#     assert repo.snapshot().meta["targets.json"].version == 1

#     # assert add new timestamp key and version bumps (all but targets)
#     repo.add_keys([test_signer2], "timestamp")
#     assert test_signer2.public_key.keyid in repo.root().roles["timestamp"].keyids
#     assert repo.root().version == 3
#     assert repo.timestamp().version == 3
#     assert repo.snapshot().version == 3
#     assert repo.targets().version == 1
#     assert repo.timestamp().snapshot_meta.version == 3
#     assert repo.snapshot().meta["root.json"].version == 3
#     assert repo.snapshot().meta["targets.json"].version == 1

#     # assert add new snapshot key and version bumps (all but targets)
#     repo.add_keys([test_signer2], "snapshot")
#     assert test_signer2.public_key.keyid in repo.root().roles["snapshot"].keyids
#     assert repo.root().version == 4
#     assert repo.timestamp().version == 4
#     assert repo.snapshot().version == 4
#     assert repo.targets().version == 1
#     assert repo.timestamp().snapshot_meta.version == 4
#     assert repo.snapshot().meta["root.json"].version == 4
#     assert repo.snapshot().meta["targets.json"].version == 1

#     # assert add new targets key and version bumps (all)
#     repo.add_keys([test_signer2], "targets")
#     assert test_signer2.public_key.keyid in repo.root().roles["targets"].keyids
#     assert repo.root().version == 5
#     assert repo.timestamp().version == 5
#     assert repo.snapshot().version == 5
#     assert repo.targets().version == 2
#     assert repo.timestamp().snapshot_meta.version == 5
#     assert repo.snapshot().meta["root.json"].version == 5
#     assert repo.snapshot().meta["targets.json"].version == 2
