import pytest
from taf.exceptions import TAFError
from taf.tests.conftest import TEST_DATA_REPOS_PATH
from taf.tuf.repository import MetadataRepository

def test_get_threshold_no_delegations():
    test_group_dir = TEST_DATA_REPOS_PATH / "test-repository-tool/test-happy-path-pkcs1v15" / "taf"
    tuf_repo = MetadataRepository(test_group_dir)
    assert tuf_repo.get_role_threshold("root") == 2
    assert tuf_repo.get_role_threshold("targets") == 1
    assert tuf_repo.get_role_threshold("snapshot") == 1
    assert tuf_repo.get_role_threshold("timestamp") == 1
    with pytest.raises(TAFError):
        tuf_repo.get_role_threshold("doestexist")

def test_get_threshold_delegations():
    test_group_dir = TEST_DATA_REPOS_PATH / "test-repository-tool/test-delegated-roles-pkcs1v15" / "taf"
    tuf_repo = MetadataRepository(test_group_dir)
    assert tuf_repo.get_role_threshold("delegated_role1") == 2
    assert tuf_repo.get_role_threshold("delegated_role2") == 1
    assert tuf_repo.get_role_threshold("inner_delegated_role") == 1


