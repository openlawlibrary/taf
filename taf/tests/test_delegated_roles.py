def test_get_all_targets_roles(repositories):
    taf_delegated_roles = repositories["test-delegated-roles"]
    assert taf_delegated_roles.get_all_targets_roles() == [
        "targets",
        "delegated_role1",
        "delegated_role2",
        "inner_delegated_role",
    ]


def test_find_roles_parent(repositories):
    taf_delegated_roles = repositories["test-delegated-roles"]
    assert (
        taf_delegated_roles.find_delegated_roles_parent("delegated_role1") == "targets"
    )
    assert (
        taf_delegated_roles.find_delegated_roles_parent("delegated_role2") == "targets"
    )
    assert (
        taf_delegated_roles.find_delegated_roles_parent("inner_delegated_role")
        == "delegated_role2"
    )


def test_map_signing_roles(repositories):
    taf_delegated_roles = repositories["test-delegated-roles"]
    expected_targets_roles = {
        "dir1/delegated_role1_1.txt": "delegated_role1",
        "dir1/delegated_role1_2.txt": "delegated_role1",
        "dir2/delegated_role2_1.txt": "delegated_role2",
        "dir2/delegated_role2_1.txt": "delegated_role2",
        "dir2/inner_delegated_role.txt": "inner_delegated_role",
    }
    actual_targets_roles = taf_delegated_roles.map_signing_roles(
        expected_targets_roles.keys()
    )
    for file_name, expected_role in expected_targets_roles.items():
        assert file_name in actual_targets_roles
        assert actual_targets_roles[file_name] == expected_role


def test_find_keys_roles(
    repositories,
    delegated_role11_key,
    delegated_role12_key,
    delegated_role13_key,
    delegated_role2_key,
    inner_delegated_role_key,
):
    taf_delegated_roles = repositories["test-delegated-roles"]
    assert not len(taf_delegated_roles.find_keys_roles([delegated_role11_key]))
    assert taf_delegated_roles.find_keys_roles(
        [delegated_role11_key, delegated_role12_key]
    ) == ["delegated_role1"]
    assert taf_delegated_roles.find_keys_roles(
        [delegated_role11_key, delegated_role12_key, delegated_role13_key]
    ) == ["delegated_role1"]
    assert taf_delegated_roles.find_keys_roles([delegated_role2_key]) == [
        "delegated_role2"
    ]
    assert taf_delegated_roles.find_keys_roles([inner_delegated_role_key]) == [
        "inner_delegated_role"
    ]


def test_sort_roles_targets_for_filenames(repositories):
    taf_delegated_roles = repositories["test-delegated-roles"]
    targets_files_by_roles = taf_delegated_roles.sort_roles_targets_for_filenames()
    assert "delegated_role1" in targets_files_by_roles
    for target_file in targets_files_by_roles["delegated_role1"]:
        assert target_file in [
            "dir1/delegated_role1_1.txt",
            "dir1/delegated_role1_2.txt",
        ]

    assert "delegated_role2" in targets_files_by_roles
    for target_file in targets_files_by_roles["delegated_role2"]:
        assert target_file in [
            "dir2/delegated_role2_1.txt",
            "dir2/delegated_role2_2.txt",
        ]
    assert "inner_delegated_role" in targets_files_by_roles
    assert targets_files_by_roles["inner_delegated_role"] == [
        "dir2/inner_delegated_role.txt"
    ]


def test_get_role_from_target_paths(repositories):
    taf_delegated_roles = repositories["test-delegated-roles"]

    target_paths_with_same_role = [
        "dir1/delegated_role1_1.txt",
        "dir1/delegated_role1_2.txt",
    ]
    role = taf_delegated_roles.get_role_from_target_paths(target_paths_with_same_role)
    assert role == "delegated_role1"

    target_paths_with_different_role = [
        "dir2/delegated_role2_1.txt",
        "dir2/inner_delegated_role.txt",
    ]
    role = taf_delegated_roles.get_role_from_target_paths(
        target_paths_with_different_role
    )
    assert role is None
