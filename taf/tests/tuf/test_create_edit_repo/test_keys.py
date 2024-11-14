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

    tuf_repo.load_signers(signers_with_delegations)
    added_keys, already_added_keys, invalid_keys = tuf_repo.add_metadata_keys(roles_keys)
    assert len(added_keys) == 3
    assert len(already_added_keys) == 0
    assert len(invalid_keys) == 0

    assert _get_legacy_keyid(new_targets_key) in tuf_repo.root().roles["targets"].keyids
    assert _get_legacy_keyid(new_snapshot_key) in tuf_repo.root().roles["snapshot"].keyids
    assert _get_legacy_keyid(new_targets_key) in tuf_repo.root().keys
    assert _get_legacy_keyid(new_snapshot_key) in tuf_repo.root().keys
    assert _get_legacy_keyid(new_delegated_key) in tuf_repo._role_obj("delegated_role").keyids
    assert tuf_repo.root().version == 2
    assert tuf_repo.targets().version == 2


    assert tuf_repo.snapshot().version == 1
    assert tuf_repo._signed_obj("delegated_role").version == 1
    assert tuf_repo.timestamp().snapshot_meta.version == 1
    assert tuf_repo.snapshot().meta["root.json"].version == 1
    assert tuf_repo.snapshot().meta["targets.json"].version == 1

    tuf_repo.update_snapshot_and_timestamp()
    assert tuf_repo.snapshot().version == 2
    assert tuf_repo._signed_obj("delegated_role").version == 1
    assert tuf_repo.timestamp().snapshot_meta.version == 2
    assert tuf_repo.snapshot().meta["root.json"].version == 2
    assert tuf_repo.snapshot().meta["targets.json"].version == 2

    new_root_key = public_keys["root"][0]
    roles_keys = {
        "root": [new_root_key],
    }
    # assert add new root key and version bumps (all but targets)
    tuf_repo.add_metadata_keys(roles_keys)


    assert _get_legacy_keyid(new_root_key) in tuf_repo.root().roles["root"].keyids
    assert _get_legacy_keyid(new_root_key) in tuf_repo.root().keys
    assert tuf_repo.root().version == 3
    assert tuf_repo.targets().version == 2

    assert tuf_repo.snapshot().version == 2
    assert tuf_repo.timestamp().snapshot_meta.version == 2
    assert tuf_repo.snapshot().meta["root.json"].version == 2
    assert tuf_repo.snapshot().meta["targets.json"].version == 2

    tuf_repo.update_snapshot_and_timestamp()
    assert tuf_repo.snapshot().version == 3
    assert tuf_repo.timestamp().snapshot_meta.version == 3
    assert tuf_repo.snapshot().meta["root.json"].version == 3
    assert tuf_repo.snapshot().meta["targets.json"].version == 2


    # assert add new timestamp key and version bumps (all but targets)
    new_timestamp_key = public_keys["timestamp"][0]
    roles_keys = {
        "timestamp": [new_timestamp_key],
    }
    # assert add new root key and version bumps (all but targets)
    tuf_repo.add_metadata_keys(roles_keys)
    tuf_repo.update_snapshot_and_timestamp()

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
    new_snapshot_key = public_keys["timestamp"][0] # make sure this key was not already added
    roles_keys = {
        "snapshot": [new_snapshot_key],
    }
    # assert add new root key and version bumps (all but targets)
    tuf_repo.add_metadata_keys(roles_keys)
    tuf_repo.update_snapshot_and_timestamp()

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
    tuf_repo.add_metadata_keys(roles_keys)
    tuf_repo.update_snapshot_and_timestamp()

    assert _get_legacy_keyid(new_targets_key) in tuf_repo.root().roles["targets"].keyids
    assert _get_legacy_keyid(new_targets_key) in tuf_repo.root().keys
    assert tuf_repo.root().version == 6
    assert tuf_repo.timestamp().version == 6
    assert tuf_repo.snapshot().version == 6
    assert tuf_repo.targets().version == 2
    assert tuf_repo.snapshot().meta["root.json"].version == 6
    assert tuf_repo.snapshot().meta["targets.json"].version == 2

    # try adding again, no metadata should be updated
    tuf_repo.add_metadata_keys(roles_keys)
    tuf_repo.update_snapshot_and_timestamp()

    assert _get_legacy_keyid(new_targets_key) in tuf_repo.root().roles["targets"].keyids
    assert _get_legacy_keyid(new_targets_key) in tuf_repo.root().keys
    assert tuf_repo.root().version == 6
    assert tuf_repo.timestamp().version == 6
    assert tuf_repo.snapshot().version == 6
    assert tuf_repo.targets().version == 2
    assert tuf_repo.snapshot().meta["root.json"].version == 6
    assert tuf_repo.snapshot().meta["targets.json"].version == 2


def test_revoke_metadata_key(tuf_repo, signers_with_delegations, public_keys_with_delegations, public_keys):
    tuf_repo.load_signers(signers_with_delegations)
    targets_key1 = public_keys_with_delegations["targets"][0]
    targets_key2 = public_keys_with_delegations["targets"][1]
    targets_key1_id = _get_legacy_keyid(targets_key1)
    targets_key2_id = _get_legacy_keyid(targets_key2)

    assert targets_key1_id in tuf_repo.root().roles["targets"].keyids
    assert targets_key1_id in tuf_repo.root().keys

    removed_from_roles, not_added_roles, less_than_threshold_roles = tuf_repo.revoke_metadata_key(targets_key1_id, ["targets"])
    assert len(removed_from_roles) == 1
    assert len(not_added_roles) == 0
    assert len(less_than_threshold_roles) == 0

    assert targets_key1_id not in tuf_repo.root().roles["targets"].keyids
    assert targets_key1_id not in tuf_repo.root().keys
    assert len(tuf_repo._role_obj("targets").keyids) == 1
    assert tuf_repo.root().version == 2
    assert tuf_repo.targets().version == 1

    assert tuf_repo.timestamp().version == 1
    assert tuf_repo.snapshot().version == 1

    tuf_repo.update_snapshot_and_timestamp()
    assert tuf_repo.timestamp().version == 2
    assert tuf_repo.snapshot().version == 2
    # the second key cannot be removed because there is only one key left now
    removed_from_roles, not_added_roles, less_than_threshold_roles = tuf_repo.revoke_metadata_key(targets_key2_id, ["targets"])

    assert targets_key2_id in tuf_repo.root().roles["targets"].keyids
    assert targets_key2_id in tuf_repo.root().keys
    assert len(removed_from_roles) == 0
    assert len(not_added_roles) == 0
    assert len(less_than_threshold_roles) == 1

    # try to remove key
    # will not be possible, number == threshold
    delegated_key1 = public_keys_with_delegations["delegated_role"][0]
    delegated_key1_id = _get_legacy_keyid(delegated_key1)

    assert tuf_repo.root().version == 2
    assert tuf_repo.timestamp().version == 2
    assert tuf_repo.snapshot().version == 2
    assert tuf_repo.targets().version == 1

    assert delegated_key1_id in tuf_repo._role_obj("delegated_role").keyids
    removed_from_roles, not_added_roles, less_than_threshold_roles = tuf_repo.revoke_metadata_key(delegated_key1_id, ["delegated_role"])
    assert len(removed_from_roles) == 0
    assert len(not_added_roles) == 0
    assert len(less_than_threshold_roles) == 1
    assert delegated_key1_id in tuf_repo._role_obj("delegated_role").keyids

    # add a key
    new_delegated_key = public_keys["targets"][0]

    roles_keys = {
        "delegated_role": [new_delegated_key],
    }
    new_delegated_key_id = _get_legacy_keyid(new_delegated_key)

    tuf_repo.add_metadata_keys(roles_keys)
    tuf_repo.update_snapshot_and_timestamp()
    assert new_delegated_key_id in tuf_repo._role_obj("delegated_role").keyids

    assert tuf_repo.root().version == 2
    assert tuf_repo.timestamp().version == 3
    assert tuf_repo.snapshot().version == 3
    assert tuf_repo.targets().version == 2

    assert delegated_key1_id in tuf_repo._role_obj("delegated_role").keyids
    # now try removing one of delegated keys again
    removed_from_roles, not_added_roles, less_than_threshold_roles = tuf_repo.revoke_metadata_key(delegated_key1_id, ["delegated_role"])
    tuf_repo.update_snapshot_and_timestamp()
    assert len(removed_from_roles) == 1
    assert len(not_added_roles) == 0
    assert len(less_than_threshold_roles) == 0
    assert delegated_key1_id not in tuf_repo._role_obj("delegated_role").keyids

    assert tuf_repo.root().version == 2
    assert tuf_repo.timestamp().version == 4
    assert tuf_repo.snapshot().version == 4
    assert tuf_repo.targets().version == 3
