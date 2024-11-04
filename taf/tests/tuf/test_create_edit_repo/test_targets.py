


from taf.models.converter import from_dict
from taf.models.types import RolesKeysData
from taf.tuf.repository import MetadataRepository, TargetFile


def test_add_target_files(repo_path, signers, no_yubikeys_input):
    # Create new metadata repository
    tuf_repo = MetadataRepository(repo_path)
    roles_keys_data = from_dict(no_yubikeys_input, RolesKeysData)
    tuf_repo.create(roles_keys_data, signers)


    # assert add target file and correct version bumps
    path1 = "foo.txt"
    tuf_repo.add_target_files_to_role({path1: {"target": "foo"}})
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
    path2 = "test.txt"
    custom =  {"custom_attr": "custom_val"}
    tuf_repo.add_target_files_to_role({path2: {"target": "test", "custom": custom}})
    assert (tuf_repo._path / "targets" / path2).is_file()
    assert tuf_repo.targets().targets[path2].length > 0
    assert tuf_repo.targets().targets[path2].custom ==  custom

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
