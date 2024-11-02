


from taf.models.converter import from_dict
from taf.models.types import RolesKeysData
from taf.tuf.repository import MetadataRepository, TargetFile


def test_add_target_files(repo_path, signers, no_yubikeys_input):
    # Create new metadata repository
    tuf_repo = MetadataRepository(repo_path)
    roles_keys_data = from_dict(no_yubikeys_input, RolesKeysData)
    tuf_repo.create(roles_keys_data, signers)

    target_file = TargetFile.from_data("foo.txt", b"foo", ["sha256", "sha512"])

    # assert add target file and correct version bumps
    tuf_repo.add_target_files_to_role([target_file])
    assert tuf_repo.targets().targets[target_file.path] == target_file
    assert tuf_repo.root().version == 1
    assert tuf_repo.timestamp().version == 2
    assert tuf_repo.snapshot().version == 2
    assert tuf_repo.targets().version == 2
    assert tuf_repo.timestamp().snapshot_meta.version == 2
    assert tuf_repo.snapshot().meta["root.json"].version == 1
    assert tuf_repo.snapshot().meta["targets.json"].version == 2

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
