import pytest
import datetime
from taf.exceptions import TAFError


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


def test_get_threshold_no_delegations(tuf_repo_no_delegations):
    assert tuf_repo_no_delegations.get_role_threshold("root") == 2
    assert tuf_repo_no_delegations.get_role_threshold("targets") == 1
    assert tuf_repo_no_delegations.get_role_threshold("snapshot") == 1
    assert tuf_repo_no_delegations.get_role_threshold("timestamp") == 1
    with pytest.raises(TAFError):
        tuf_repo_no_delegations.get_role_threshold("doestexist")


def test_get_threshold_delegations(tuf_repo_with_delegations):
    assert tuf_repo_with_delegations.get_role_threshold("root") == 2
    assert tuf_repo_with_delegations.get_role_threshold("targets") == 1
    assert tuf_repo_with_delegations.get_role_threshold("snapshot") == 1
    assert tuf_repo_with_delegations.get_role_threshold("timestamp") == 1
    assert tuf_repo_with_delegations.get_role_threshold("delegated_role") == 2
    assert tuf_repo_with_delegations.get_role_threshold("inner_role") == 1


def test_get_expiration_date(tuf_repo_with_delegations):
    today = datetime.datetime.now(datetime.timezone.utc).date()
    assert tuf_repo_with_delegations.get_expiration_date(
        "root"
    ).date() == today + datetime.timedelta(days=365)
    assert tuf_repo_with_delegations.get_expiration_date(
        "targets"
    ).date() == today + datetime.timedelta(days=90)
    assert tuf_repo_with_delegations.get_expiration_date(
        "delegated_role"
    ).date() == today + datetime.timedelta(days=90)


def test_get_all_target_roles_no_delegations(tuf_repo_no_delegations):
    assert tuf_repo_no_delegations.get_all_targets_roles() == ["targets"]


def test_get_all_target_roles_with_delegations(tuf_repo_with_delegations):
    actual = tuf_repo_with_delegations.get_all_targets_roles()
    assert len(actual) == 3
    assert set(actual) == {"targets", "delegated_role", "inner_role"}


def test_get_all_roles_with_delegations(tuf_repo_with_delegations):
    actual = tuf_repo_with_delegations.get_all_roles()
    assert len(actual) == 6
    assert set(actual) == {
        "root",
        "snapshot",
        "timestamp",
        "targets",
        "delegated_role",
        "inner_role",
    }


def test_find_delegated_roles_parent(tuf_repo_with_delegations):
    assert (
        tuf_repo_with_delegations.find_delegated_roles_parent("delegated_role")
        == "targets"
    )
    assert (
        tuf_repo_with_delegations.find_delegated_roles_parent("inner_role")
        == "delegated_role"
    )


def test_check_if_role_exists(tuf_repo_with_delegations):
    assert tuf_repo_with_delegations.check_if_role_exists("targets")
    assert tuf_repo_with_delegations.check_if_role_exists("inner_role")
    assert not tuf_repo_with_delegations.check_if_role_exists("doesntexist")


def test_check_roles_expiration_dates(tuf_repo_no_delegations):
    (
        expired_dict,
        will_expire_dict,
    ) = tuf_repo_no_delegations.check_roles_expiration_dates()
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
    test_target_paths = ["dir1/file1.txt", "dir2/path2", "other"]
    actual = tuf_repo_with_delegations.map_signing_roles(test_target_paths)
    assert actual["dir1/file1.txt"] == "delegated_role"
    assert actual["dir2/path2"] == "inner_role"
    assert actual["other"] == "targets"


def test_get_role_from_target_paths(tuf_repo_with_delegations):
    assert (
        tuf_repo_with_delegations.get_role_from_target_paths(
            ["dir1/file1.txt", "dir1/file2.txt"]
        )
        == "delegated_role"
    )


def test_find_keys_roles(tuf_repo_with_delegations, public_keys_with_delegations):
    target_keys = public_keys_with_delegations["targets"]
    delegated_role_keys = public_keys_with_delegations["delegated_role"]
    actual = tuf_repo_with_delegations.find_keys_roles(
        target_keys + delegated_role_keys
    )
    assert actual == ["targets", "delegated_role"]
    actual = tuf_repo_with_delegations.find_keys_roles(
        target_keys[2:] + delegated_role_keys
    )
    assert actual == ["delegated_role"]
    root_keys = public_keys_with_delegations["root"]
    actual = tuf_repo_with_delegations.find_keys_roles(root_keys)
    assert actual == ["root"]


def test_find_associated_roles_of_key(
    tuf_repo_with_delegations, public_keys_with_delegations
):
    for role in (
        "root",
        "targets",
        "snapshot",
        "timestamp",
        "delegated_role",
        "inner_role",
    ):
        key = public_keys_with_delegations[role][0]
        assert tuf_repo_with_delegations.find_associated_roles_of_key(key) == [role]


def test_all_target_files(tuf_repo_with_delegations):
    # this method is expected to list all target files inside the targets directory
    actual = tuf_repo_with_delegations.all_target_files()
    assert actual == {"test2", "test1", "dir2/path2", "dir1/path1", "dir2/path1"}


def test_get_signed_target_files_of_roles(tuf_repo_with_delegations):
    actual = tuf_repo_with_delegations.get_signed_target_files_of_roles()
    assert actual == {"test2", "test1", "dir2/path2", "dir1/path1", "dir2/path1"}
    actual = tuf_repo_with_delegations.get_signed_target_files_of_roles(["targets"])
    assert actual == {"test2", "test1"}
    actual = tuf_repo_with_delegations.get_signed_target_files_of_roles(["targets"])
    assert actual == {"test2", "test1"}
    actual = tuf_repo_with_delegations.get_signed_target_files_of_roles(
        ["targets", "delegated_role"]
    )
    assert actual == {"test2", "test1", "dir1/path1", "dir2/path1"}


def test_get_signed_target_files(tuf_repo_with_delegations):
    actual = tuf_repo_with_delegations.get_signed_target_files()
    assert actual == {"test2", "test1", "dir2/path2", "dir1/path1", "dir2/path1"}


def test_get_signed_targets_with_custom_data(tuf_repo_with_delegations):
    actual = tuf_repo_with_delegations.get_signed_targets_with_custom_data()
    assert actual == {
        "test1": {},
        "test2": {},
        "dir1/path1": {"custom_attr1": "custom_val1"},
        "dir2/path1": {"custom_attr2": "custom_val2"},
        "dir2/path2": {},
    }


def test_get_target_file_custom_data(tuf_repo_with_delegations):
    actual = tuf_repo_with_delegations.get_target_file_custom_data("dir1/path1")
    assert actual == {"custom_attr1": "custom_val1"}
    actual = tuf_repo_with_delegations.get_target_file_custom_data("dir2/path1")
    assert actual == {"custom_attr2": "custom_val2"}

    tuf_repo_with_delegations.get_target_file_custom_data("doesntexist") is None


def test_get_target_file_hashes(tuf_repo_with_delegations):
    hash_value = tuf_repo_with_delegations.get_target_file_hashes(
        "dir1/path1", "sha256"
    )
    assert len(hash_value) == 64
    hash_value = tuf_repo_with_delegations.get_target_file_hashes(
        "dir1/path1", "sha512"
    )
    assert len(hash_value) == 128

    tuf_repo_with_delegations.get_target_file_hashes("doesntexist") is None


def test_get_key_length_and_scheme_from_metadata(tuf_repo_with_delegations):
    keyid = tuf_repo_with_delegations._role_obj("targets").keyids[0]
    actual = tuf_repo_with_delegations.get_key_length_and_scheme_from_metadata(
        "root", keyid
    )
    key, scheme = actual
    assert key is not None
    assert scheme == "rsa-pkcs1v15-sha256"


def test_generate_roles_description(tuf_repo_with_delegations):
    actual = tuf_repo_with_delegations.generate_roles_description()
    roles_data = actual["roles"]
    root_data = roles_data["root"]
    assert root_data["threshold"] == 2
    assert root_data["number"] == 3
    assert root_data["scheme"] == "rsa-pkcs1v15-sha256"
    assert root_data["length"] == 3072
    targets_data = roles_data["targets"]
    assert targets_data["threshold"] == 1
    assert targets_data["number"] == 2
    assert targets_data["scheme"] == "rsa-pkcs1v15-sha256"
    assert targets_data["length"] == 3072
    snapshot_data = roles_data["snapshot"]
    assert snapshot_data["threshold"] == 1
    assert snapshot_data["number"] == 1
    assert snapshot_data["scheme"] == "rsa-pkcs1v15-sha256"
    assert snapshot_data["length"] == 3072
    timestamp_data = roles_data["timestamp"]
    assert timestamp_data["threshold"] == 1
    assert timestamp_data["number"] == 1
    assert timestamp_data["scheme"] == "rsa-pkcs1v15-sha256"
    assert timestamp_data["length"] == 3072
    assert targets_data["delegations"]
    delegated_role_data = targets_data["delegations"]["delegated_role"]
    assert delegated_role_data["threshold"] == 2
    assert delegated_role_data["number"] == 2
    assert delegated_role_data["scheme"] == "rsa-pkcs1v15-sha256"
    assert delegated_role_data["length"] == 3072
    assert delegated_role_data["delegations"]
    inner_role_data = delegated_role_data["delegations"]["inner_role"]
    assert inner_role_data["threshold"] == 1
    assert inner_role_data["number"] == 1
    assert inner_role_data["scheme"] == "rsa-pkcs1v15-sha256"
    assert inner_role_data["length"] == 3072


def test_sort_roles_targets_for_filenames(tuf_repo_with_delegations):
    actual = tuf_repo_with_delegations.sort_roles_targets_for_filenames()
    assert actual["targets"] == ["test1", "test2"]
    assert actual["delegated_role"] == ["dir1/path1", "dir2/path1"]
    assert actual["inner_role"] == ["dir2/path2"]


def test_is_valid_metadata_key(tuf_repo_with_delegations, public_keys_with_delegations):
    for role in (
        "root",
        "targets",
        "snapshot",
        "timestamp",
        "delegated_role",
        "inner_role",
    ):
        key = public_keys_with_delegations[role][0]
        assert tuf_repo_with_delegations.is_valid_metadata_key(role, key)
        assert tuf_repo_with_delegations.is_valid_metadata_key(
            role, key.keyval["public"]
        )

    assert not tuf_repo_with_delegations.is_valid_metadata_key(
        "root", public_keys_with_delegations["targets"][0]
    )

    with pytest.raises(TAFError):
        tuf_repo_with_delegations.is_valid_metadata_key("root", "123456")


def test_get_signable_metadata(tuf_repo_with_delegations):
    actual = tuf_repo_with_delegations.get_signable_metadata("root")
    assert len(actual) == 7
    for key in (
        "_type",
        "version",
        "spec_version",
        "expires",
        "consistent_snapshot",
        "keys",
        "roles",
    ):
        assert key in actual


def test_roles_targets_for_filenames(tuf_repo_with_delegations):
    target_filenames = ["dir2/path1", "dir2/path2", "test"]
    actual = tuf_repo_with_delegations.roles_targets_for_filenames(target_filenames)
    assert actual == {
        "delegated_role": ["dir2/path1"],
        "inner_role": ["dir2/path2"],
        "targets": ["test"],
    }
