def test_add_keys(tuf_repo, public_keys):

    # there public keys were loaded from a different keystore
    # (are used to instantiate a repositoru with no delegations)

    new_key = public_keys["targets"][0]
    tuf_repo.add_metadata_key("targets", new_key)



    # assert add new root key and version bumps (all but targets)
    # assert test_signer2.public_key.keyid in repo.root().keys
    # assert test_signer2.public_key.keyid in repo.root().roles["root"].keyids
    # assert repo.root().version == 2
    # assert repo.timestamp().version == 2
    # assert repo.snapshot().version == 2
    # assert repo.targets().version == 1
    # assert repo.timestamp().snapshot_meta.version == 2
    # assert repo.snapshot().meta["root.json"].version == 2
    # assert repo.snapshot().meta["targets.json"].version == 1