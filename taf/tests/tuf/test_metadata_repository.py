import datetime
import pytest
from taf.exceptions import TAFError
from taf.tests.conftest import TEST_DATA_REPOS_PATH
from taf.tuf.repository import MetadataRepository


def test_open(tuf_repo_with_delegations):
    # assert existing role metadata can be opened
    for role in [
        "root",
        "timestamp",
        "snapshot",
        "targets",
        "delegated_role",
        "inner_role",
    ]:
        assert tuf_repo_with_delegations.open(role)

    # assert non-existing role metadata cannot be opened
    with pytest.raises(TAFError):
        tuf_repo_with_delegations.open("foo")


def test_get_threshold_no_delegations(tuf_repo):
    assert tuf_repo.get_role_threshold("root") == 2
    assert tuf_repo.get_role_threshold("targets") == 1
    assert tuf_repo.get_role_threshold("snapshot") == 1
    assert tuf_repo.get_role_threshold("timestamp") == 1
    with pytest.raises(TAFError):
        tuf_repo.get_role_threshold("doestexist")


def test_get_threshold_delegations(tuf_repo_with_delegations):
    assert tuf_repo_with_delegations.get_role_threshold("root") == 2
    assert tuf_repo_with_delegations.get_role_threshold("targets") == 1
    assert tuf_repo_with_delegations.get_role_threshold("snapshot") == 1
    assert tuf_repo_with_delegations.get_role_threshold("timestamp") == 1
    assert tuf_repo_with_delegations.get_role_threshold("delegated_role") == 2
    assert tuf_repo_with_delegations.get_role_threshold("inner_role") == 1


def test_get_expiration_date(tuf_repo_with_delegations):
    today = datetime.datetime.now(datetime.timezone.utc).date()
    assert tuf_repo_with_delegations.get_expiration_date("root").date() == today + datetime.timedelta(days=365)
    assert tuf_repo_with_delegations.get_expiration_date("targets").date() ==  today + datetime.timedelta(days=90)
    assert tuf_repo_with_delegations.get_expiration_date("delegated_role").date() == today + datetime.timedelta(days=90)


def test_get_all_target_roles_no_delegations(tuf_repo):
    assert tuf_repo.get_all_targets_roles() == ["targets"]


def test_get_all_target_roles_with_delegations(tuf_repo_with_delegations):
    actual = tuf_repo_with_delegations.get_all_targets_roles()
    assert len(actual) == 3
    assert set(actual) == {"targets", "delegated_role", "inner_role"}


def test_get_all_roles_with_delegations(tuf_repo_with_delegations):
    actual = tuf_repo_with_delegations.get_all_roles()
    assert len(actual) == 6
    assert set(actual) == {"root", "snapshot", "timestamp", "targets",  "delegated_role", "inner_role"}


def test_find_delegated_roles_parent(tuf_repo_with_delegations):
    assert tuf_repo_with_delegations.find_delegated_roles_parent("delegated_role") == "targets"
    assert tuf_repo_with_delegations.find_delegated_roles_parent("inner_role") == "delegated_role"


def test_check_if_role_exists(tuf_repo_with_delegations):
    assert tuf_repo_with_delegations.check_if_role_exists("targets")
    assert tuf_repo_with_delegations.check_if_role_exists("inner_role")
    assert not tuf_repo_with_delegations.check_if_role_exists("doesntexist")


def test_check_roles_expiration_dates(tuf_repo):
    expired_dict, will_expire_dict = tuf_repo.check_roles_expiration_dates()
    assert not len(expired_dict)
    assert "root" not in will_expire_dict
    assert "targets" not in will_expire_dict
    assert "timestamp" in will_expire_dict


def test_get_role_paths(tuf_repo_with_delegations):
    actual = tuf_repo_with_delegations.get_role_paths("delegated_role")
    assert actual == ["dir1/*", "dir2/path1"]
    actual = tuf_repo_with_delegations.get_role_paths("inner_role")
    assert actual == ["dir2/path2"]


def test_signing_roles(tuf_repo_with_delegations):
    test_target_paths = [
        "dir1/file1.txt", "dir2/path2", "other"
    ]
    actual = tuf_repo_with_delegations.map_signing_roles(test_target_paths)
    assert actual["dir1/file1.txt"] == "delegated_role"
    assert actual["dir2/path2"] == "inner_role"
    assert actual["other"] == "targets"


def test_get_role_from_target_paths(tuf_repo_with_delegations):
    assert tuf_repo_with_delegations.get_role_from_target_paths(["dir1/file1.txt", "dir1/file2.txt"]) == "delegated_role"

# def test_find_keys_roles(targets_key):
#     test_group_dir = TEST_DATA_REPOS_PATH / "test-repository-tool/test-delegated-roles-pkcs1v15" / "taf"
#     tuf_repo = MetadataRepository(test_group_dir)
#     tuf_repo.find_keys_roles([targets_key])


# def test_all_target_files():
#     test_group_dir = TEST_DATA_REPOS_PATH / "test-repository-tool/test-happy-path-pkcs1v15" / "taf"
#     tuf_repo = MetadataRepository(test_group_dir)
#     actual = tuf_repo.all_target_files()
#     assert len(actual) == 3
#     assert actual == {'branch', 'dummy/target_dummy_repo', 'repositories.json'}