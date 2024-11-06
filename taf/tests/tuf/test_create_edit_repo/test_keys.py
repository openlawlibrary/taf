from taf.tuf.keys import _get_legacy_keyid


def test_add_metadata_keys(tuf_repo, signers_with_delegations, public_keys):

    # there public keys were loaded from a different keystore
    # (are used to instantiate a repositoru with no delegations)

    new_targets_key = public_keys["targets"][0]
    new_snapshot_key = public_keys["snapshot"][0]
    new_delegated_key = new_targets_key

    roles_keys = {
        "targets": [new_targets_key],
        "delegated_role": [new_delegated_key],
        "snapshot": [new_snapshot_key]
    }

    tuf_repo.add_metadata_keys(signers_with_delegations, roles_keys)

    assert _get_legacy_keyid(new_targets_key) in tuf_repo.root().roles["targets"].keyids
    assert _get_legacy_keyid(new_snapshot_key) in tuf_repo.root().roles["snapshot"].keyids
    assert _get_legacy_keyid(new_targets_key) in tuf_repo.root().keys
    assert _get_legacy_keyid(new_snapshot_key) in tuf_repo.root().keys
    assert tuf_repo.root().version == 2
    assert tuf_repo.timestamp().version == 2
    assert tuf_repo.snapshot().version == 2
    assert tuf_repo.targets().version == 2
    assert tuf_repo._signed_obj("delegated_role").version == 1
    assert tuf_repo.timestamp().snapshot_meta.version == 2
    assert tuf_repo.snapshot().meta["root.json"].version == 2
    assert tuf_repo.snapshot().meta["targets.json"].version == 2


    new_root_key = public_keys["root"][0]
    roles_keys = {
        "root": [new_root_key],
    }
    # assert add new root key and version bumps (all but targets)
    tuf_repo.add_metadata_keys(signers_with_delegations, roles_keys)

    assert _get_legacy_keyid(new_root_key) in tuf_repo.root().roles["root"].keyids
    assert _get_legacy_keyid(new_root_key) in tuf_repo.root().keys
    assert tuf_repo.root().version == 3
    assert tuf_repo.timestamp().version == 3
    assert tuf_repo.snapshot().version == 3
    assert tuf_repo.targets().version == 2
    assert tuf_repo.timestamp().snapshot_meta.version == 3
    assert tuf_repo.snapshot().meta["root.json"].version == 3
    assert tuf_repo.snapshot().meta["targets.json"].version == 2

    # assert add new timestamp key and version bumps (all but targets)
    new_timestamp_key = public_keys["timestamp"][0]
    roles_keys = {
        "timestamp": [new_timestamp_key],
    }
    # assert add new root key and version bumps (all but targets)
    tuf_repo.add_metadata_keys(signers_with_delegations, roles_keys)

    assert _get_legacy_keyid(new_timestamp_key) in tuf_repo.root().roles["timestamp"].keyids
    assert _get_legacy_keyid(new_timestamp_key) in tuf_repo.root().keys
    assert tuf_repo.root().version == 4
    assert tuf_repo.timestamp().version == 4
    assert tuf_repo.snapshot().version == 4
    assert tuf_repo.targets().version == 2
    assert tuf_repo.timestamp().snapshot_meta.version == 4
    assert tuf_repo.snapshot().meta["root.json"].version == 4
    assert tuf_repo.snapshot().meta["targets.json"].version == 2

    # assert add new timestamp key and version bumps (all but targets)
    new_snapshot_key = public_keys["snapshot"][0]
    roles_keys = {
        "snapshot": [new_snapshot_key],
    }
    # assert add new root key and version bumps (all but targets)
    tuf_repo.add_metadata_keys(signers_with_delegations, roles_keys)

    assert _get_legacy_keyid(new_snapshot_key) in tuf_repo.root().roles["snapshot"].keyids
    assert _get_legacy_keyid(new_snapshot_key) in tuf_repo.root().keys
    assert tuf_repo.root().version == 5
    assert tuf_repo.snapshot().version == 5
    assert tuf_repo.snapshot().version == 5
    assert tuf_repo.targets().version == 2
    assert tuf_repo.snapshot().meta["root.json"].version == 5
    assert tuf_repo.snapshot().meta["targets.json"].version == 2

        # assert add new timestamp key and version bumps (all but targets)
    new_targets_key = public_keys["root"][1]
    roles_keys = {
        "targets": [new_targets_key],
    }
    # assert add new root key and version bumps (all but targets)
    tuf_repo.add_metadata_keys(signers_with_delegations, roles_keys)

    assert _get_legacy_keyid(new_targets_key) in tuf_repo.root().roles["targets"].keyids
    assert _get_legacy_keyid(new_targets_key) in tuf_repo.root().keys
    assert tuf_repo.root().version == 6
    assert tuf_repo.timestamp().version == 6
    assert tuf_repo.snapshot().version == 6
    assert tuf_repo.targets().version == 3
    assert tuf_repo.snapshot().meta["root.json"].version == 6
    assert tuf_repo.snapshot().meta["targets.json"].version == 3
