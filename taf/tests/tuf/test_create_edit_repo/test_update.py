
import datetime

from taf.models.types import TargetsRole


def test_update_expiration_date(tuf_repo, signers_with_delegations):

    assert tuf_repo.root().version == 1
    today = datetime.datetime.now(datetime.timezone.utc).date()
    assert tuf_repo.get_expiration_date("root").date() == today + datetime.timedelta(days=365)
    tuf_repo.set_metadata_expiration_date("root", signers_with_delegations["root"], interval=730)
    assert tuf_repo.get_expiration_date("root").date() == today + datetime.timedelta(days=730)
    assert tuf_repo.root().version == 2
    # timestamp and snapshot are not updated here
    assert tuf_repo.timestamp().version == 1
    assert tuf_repo.snapshot().version == 1


def test_add_delegated_paths(tuf_repo):

    new_paths = ["new", "paths"]
    tuf_repo.add_path_to_delegated_role(role="delegated_role", paths=new_paths)

    assert tuf_repo.root().version == 1
    assert tuf_repo.targets().version == 2
    assert tuf_repo.timestamp().version == 1
    assert tuf_repo.snapshot().version == 1

    for path in new_paths:
        assert path in tuf_repo.get_delegations_of_role("targets")["delegated_role"].paths


def test_add_new_role(tuf_repo, signers):
    role_name = "test"
    targets_parent_role = TargetsRole()
    paths = ["test1", "test2"]
    threshold = 2
    keys_number = 2

    role_signers = {role_name: [signers["targets"][0], signers["snapshot"][0]]}
    new_role = TargetsRole(name=role_name,parent=targets_parent_role,paths=paths,number=keys_number,threshold=threshold, yubikey=False )
    tuf_repo.create_delegated_role([new_role], role_signers)
    assert tuf_repo.targets().version == 2
    assert role_name in tuf_repo.targets().delegations.roles
    new_role_obj = tuf_repo.open(role_name)
    assert new_role_obj
    assert tuf_repo._role_obj(role_name).threshold == threshold

    tuf_repo.add_new_roles_to_snapshot([role_name])
    assert tuf_repo.snapshot().version == 2
    assert f"{role_name}.json" in tuf_repo.snapshot().meta


def test_remove_delegated_paths(tuf_repo):

    paths_to_remvoe = ["dir2/path1"]
    tuf_repo.remove_delegated_paths({"delegated_role": paths_to_remvoe})

    assert tuf_repo.root().version == 1
    assert tuf_repo.targets().version == 2
    assert tuf_repo.timestamp().version == 1
    assert tuf_repo.snapshot().version == 1

    for path in paths_to_remvoe:
        assert path not in tuf_repo.get_delegations_of_role("targets")["delegated_role"].paths

