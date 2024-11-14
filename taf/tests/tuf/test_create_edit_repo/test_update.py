
import datetime


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