import datetime
import pytest
from taf.exceptions import TAFError
from taf.tests.conftest import TEST_DATA_REPOS_PATH
from taf.tuf.repository import MetadataRepository

def test_get_threshold_no_delegations(tuf_repo):
    assert tuf_repo.get_role_threshold("root") == 2
    assert tuf_repo.get_role_threshold("targets") == 1
    assert tuf_repo.get_role_threshold("snapshot") == 1
    assert tuf_repo.get_role_threshold("timestamp") == 1
    with pytest.raises(TAFError):
        tuf_repo.get_role_threshold("doestexist")

# def test_get_threshold_delegations():
#     test_group_dir = TEST_DATA_REPOS_PATH / "test-repository-tool/test-delegated-roles-pkcs1v15" / "taf"
#     tuf_repo = MetadataRepository(test_group_dir)
#     assert tuf_repo.get_role_threshold("delegated_role1") == 2
#     assert tuf_repo.get_role_threshold("delegated_role2") == 1
#     assert tuf_repo.get_role_threshold("inner_delegated_role") == 1


# def test_get_expiration_date():
#     test_group_dir = TEST_DATA_REPOS_PATH / "test-repository-tool/test-delegated-roles-pkcs1v15" / "taf"
#     tuf_repo = MetadataRepository(test_group_dir)
#     assert tuf_repo.get_expiration_date("root") ==  datetime.datetime(2021, 2, 3, 22, 50, 16, tzinfo=datetime.timezone.utc)
#     assert tuf_repo.get_expiration_date("targets") ==  datetime.datetime(2020, 5, 6, 0, 29, 6, tzinfo=datetime.timezone.utc)
#     assert tuf_repo.get_expiration_date("delegated_role1") ==  datetime.datetime(2020, 2, 5, 18, 14, 2, tzinfo=datetime.timezone.utc)


# def test_get_all_target_roles_no_delegations():
#     test_group_dir = TEST_DATA_REPOS_PATH / "test-repository-tool/test-happy-path-pkcs1v15" / "taf"
#     tuf_repo = MetadataRepository(test_group_dir)
#     assert tuf_repo.get_all_targets_roles() == ["targets"]


# def test_get_all_target_roles_with_delegations():
#     test_group_dir = TEST_DATA_REPOS_PATH / "test-repository-tool/test-delegated-roles-pkcs1v15" / "taf"
#     tuf_repo = MetadataRepository(test_group_dir)
#     actual = tuf_repo.get_all_targets_roles()
#     assert len(actual) == 4
#     assert set(actual) == {"targets", "delegated_role1", "delegated_role2", "inner_delegated_role"}


# def test_get_all_roles_with_delegations():
#     test_group_dir = TEST_DATA_REPOS_PATH / "test-repository-tool/test-delegated-roles-pkcs1v15" / "taf"
#     tuf_repo = MetadataRepository(test_group_dir)
#     actual = tuf_repo.get_all_roles()
#     assert len(actual) == 7
#     assert set(actual) == {"root", "snapshot", "timestamp", "targets", "delegated_role1", "delegated_role2", "inner_delegated_role"}

# def test_find_delegated_roles_parent():
#     test_group_dir = TEST_DATA_REPOS_PATH / "test-repository-tool/test-delegated-roles-pkcs1v15" / "taf"
#     tuf_repo = MetadataRepository(test_group_dir)
#     assert tuf_repo.find_delegated_roles_parent("delegated_role1") == "targets"
#     assert tuf_repo.find_delegated_roles_parent("delegated_role2") == "targets"
#     assert tuf_repo.find_delegated_roles_parent("inner_delegated_role") == "delegated_role2"

# def test_check_if_role_exists():
#     test_group_dir = TEST_DATA_REPOS_PATH / "test-repository-tool/test-delegated-roles-pkcs1v15" / "taf"
#     tuf_repo = MetadataRepository(test_group_dir)
#     assert tuf_repo.check_if_role_exists("targets")
#     assert tuf_repo.check_if_role_exists("inner_delegated_role")
#     assert not tuf_repo.check_if_role_exists("doesntexist")


# def test_check_roles_expiration_dates():
#     test_group_dir = TEST_DATA_REPOS_PATH / "test-repository-tool/test-delegated-roles-pkcs1v15" / "taf"
#     tuf_repo = MetadataRepository(test_group_dir)
#     expired_dict, will_expire_dict = tuf_repo.check_roles_expiration_dates()
#     assert "root" in expired_dict
#     assert "targets" in expired_dict
#     assert "delegated_role1" in expired_dict
#     assert not len(will_expire_dict)

# def test_all_target_files():
#     test_group_dir = TEST_DATA_REPOS_PATH / "test-repository-tool/test-happy-path-pkcs1v15" / "taf"
#     tuf_repo = MetadataRepository(test_group_dir)
#     actual = tuf_repo.all_target_files()
#     assert len(actual) == 3
#     assert actual == {'branch', 'dummy/target_dummy_repo', 'repositories.json'}

# def test_get_role_paths():
#     test_group_dir = TEST_DATA_REPOS_PATH / "test-repository-tool/test-delegated-roles-pkcs1v15" / "taf"
#     tuf_repo = MetadataRepository(test_group_dir)
#     actual = tuf_repo.get_role_paths("delegated_role1")
#     assert actual == ["dir1/*"]
#     actual = tuf_repo.get_role_paths("delegated_role2")
#     assert actual == ["dir2/*"]
#     actual = tuf_repo.get_role_paths("inner_delegated_role")
#     assert actual == ["dir2/inner_delegated_role.txt"]


# def test_signing_roles():
#     test_group_dir = TEST_DATA_REPOS_PATH / "test-repository-tool/test-delegated-roles-pkcs1v15" / "taf"
#     tuf_repo = MetadataRepository(test_group_dir)
#     test_target_paths = [
#         "dir1/file1.txt", "dir2/file2.txt", "dir2/inner_delegated_role.txt", "other"
#     ]
#     actual = tuf_repo.map_signing_roles(test_target_paths)
#     assert actual["dir1/file1.txt"] == "delegated_role1"
#     assert actual["dir2/file2.txt"] == "delegated_role2"
#     assert actual["dir2/inner_delegated_role.txt"] == "inner_delegated_role"
#     assert actual["other"] == "targets"


# def test_get_role_from_target_paths():
#     test_group_dir = TEST_DATA_REPOS_PATH / "test-repository-tool/test-delegated-roles-pkcs1v15" / "taf"
#     tuf_repo = MetadataRepository(test_group_dir)
#     assert tuf_repo.get_role_from_target_paths(["dir1/file1.txt", "dir1/file2.txt"]) == "delegated_role1"

# def test_find_keys_roles(targets_key):
#     test_group_dir = TEST_DATA_REPOS_PATH / "test-repository-tool/test-delegated-roles-pkcs1v15" / "taf"
#     tuf_repo = MetadataRepository(test_group_dir)
#     tuf_repo.find_keys_roles([targets_key])