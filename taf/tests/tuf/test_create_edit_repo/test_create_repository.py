import pytest
from taf.tuf.repository import MetadataRepository
from taf.models.types import RolesKeysData
from taf.models.converter import from_dict
from taf.tuf.keys import _get_legacy_keyid


def test_create_without_delegations(repo_path, signers, no_yubikeys_input):
    # Create new metadata repository
    tuf_repo = MetadataRepository(repo_path)
    roles_keys_data = from_dict(no_yubikeys_input, RolesKeysData)
    tuf_repo.create(roles_keys_data, signers)

    # assert metadata files were created
    assert sorted([f.name for f in tuf_repo.metadata_path.glob("*")]) == [
        "1.root.json",
        "root.json",
        "snapshot.json",
        "targets.json",
        "timestamp.json",
    ]

    # assert correct initial version
    assert tuf_repo.root().version == 1
    assert tuf_repo.timestamp().version == 1
    assert tuf_repo.snapshot().version == 1
    assert tuf_repo.targets().version == 1

    def _get_pub_key_ids(role):
        return [_get_legacy_keyid(signer.public_key) for signer in signers[role]]

    # assert correct top-level delegation
    for role in ("root", "timestamp", "snapshot", "targets"):
        assert tuf_repo.root().roles[role].keyids == _get_pub_key_ids(role)

    # assert correct snapshot and timestamp meta
    assert tuf_repo.timestamp().snapshot_meta.version == 1
    assert tuf_repo.snapshot().meta["root.json"].version == 1
    assert tuf_repo.snapshot().meta["targets.json"].version == 1
    assert len(tuf_repo.snapshot().meta) == 2

    # assert repo cannot be created twice
    with pytest.raises(FileExistsError):
        tuf_repo.create(roles_keys_data, signers)


def test_create_with_delegations(
    repo_path, signers_with_delegations, with_delegations_no_yubikeys_input
):
    # Create new metadata repository
    tuf_repo = MetadataRepository(repo_path)
    roles_keys_data = from_dict(with_delegations_no_yubikeys_input, RolesKeysData)
    tuf_repo.create(roles_keys_data, signers_with_delegations)

    # assert metadata files were created
    assert sorted([f.name for f in tuf_repo.metadata_path.glob("*")]) == [
        "1.root.json",
        "delegated_role.json",
        "inner_role.json",
        "root.json",
        "snapshot.json",
        "targets.json",
        "timestamp.json",
    ]

    # assert correct initial version
    assert tuf_repo.root().version == 1
    assert tuf_repo.timestamp().version == 1
    assert tuf_repo.snapshot().version == 1
    assert tuf_repo.targets().version == 1

    def _get_pub_key_ids(role):
        return [
            _get_legacy_keyid(signer.public_key)
            for signer in signers_with_delegations[role]
        ]

    # assert correct top-level delegation
    for role in ("root", "timestamp", "snapshot", "targets"):
        assert tuf_repo.root().roles[role].keyids == _get_pub_key_ids(role)

    # assert correct delegations
    assert len(tuf_repo.targets().delegations.roles) == 1
    assert "delegated_role" in tuf_repo.targets().delegations.roles

    # TODO update this if there is a better way to access delegated role of delegated role
    # tuf_repo.targets().delegations.roles is a list of DelegatedRole objects
    # DelegatedRole does not have a delegations property
    inner_role = tuf_repo.open("inner_role")
    assert inner_role

    # assert correct snapshot and timestamp meta
    assert tuf_repo.timestamp().snapshot_meta.version == 1
    assert tuf_repo.snapshot().meta["root.json"].version == 1
    assert tuf_repo.snapshot().meta["targets.json"].version == 1
    assert tuf_repo.snapshot().meta["delegated_role.json"].version == 1
    assert tuf_repo.snapshot().meta["inner_role.json"].version == 1
    assert len(tuf_repo.snapshot().meta) == 4

    # assert repo cannot be created twice
    with pytest.raises(FileExistsError):
        tuf_repo.create(roles_keys_data, signers_with_delegations)


def test_create_with_additional_public_keys(
    repo_path, signers_with_delegations, with_delegations_no_yubikeys_input, public_keys
):
    # Create new metadata repository
    tuf_repo = MetadataRepository(repo_path)
    roles_keys_data = from_dict(with_delegations_no_yubikeys_input, RolesKeysData)

    additional_verification_keys = {
        "targets": public_keys["targets"],
        "delegated_role": public_keys["snapshot"],
    }

    targets_signing_keys_num = len(signers_with_delegations["targets"])
    delegated_role_signing_keys_num = len(signers_with_delegations["delegated_role"])

    tuf_repo.create(
        roles_keys_data, signers_with_delegations, additional_verification_keys
    )

    # assert correct initial version
    assert len(tuf_repo._role_obj("targets").keyids) == targets_signing_keys_num + len(
        additional_verification_keys["targets"]
    )
    assert len(
        tuf_repo._role_obj("delegated_role").keyids
    ) == delegated_role_signing_keys_num + len(
        additional_verification_keys["delegated_role"]
    )
