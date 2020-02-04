import pytest
from pathlib import Path
from securesystemslib.interface import import_rsa_publickey_from_file



def test_find_roles_parent(taf_delegated_roles):
    assert taf_delegated_roles.find_delegated_roles_parent("delegated_role1") == "targets"
    assert taf_delegated_roles.find_delegated_roles_parent("delegated_role2") == "targets"
    assert taf_delegated_roles.find_delegated_roles_parent("inner_delegated_role") == "delegated_role2"


def test_map_signing_roles(taf_delegated_roles):
    expected_targets_roles = {
        "dir1/delegated_role1_1.txt": "delegated_role1",
        "dir1/delegated_role1_2.txt": "delegated_role1",
        "dir2/delegated_role2_1.txt": "delegated_role2",
        "dir2/delegated_role2_1.txt": "delegated_role2",
        "dir2/inner_delegated_role.txt": "inner_delegated_role",

    }
    actual_targets_roles = taf_delegated_roles.map_signing_roles(expected_targets_roles.keys())
    for file_name, expected_role in expected_targets_roles.items():
        assert file_name in actual_targets_roles
        assert actual_targets_roles[file_name] == expected_role


def test_find_keys_roles(taf_delegated_roles, delegated_roles_keystore):
    delegated_role1_keys = [_load_roles_pub_key(delegated_roles_keystore, f"delegated_role1{counter}") for counter in range(1,4)]
    delegated_role2_keys = [_load_roles_pub_key(delegated_roles_keystore, "delegated_role2")]
    inner_delegated_role_keys = [_load_roles_pub_key(delegated_roles_keystore, "inner_delegated_role")]
    assert len(delegated_role1_keys) == 3
    
    # assert taf_delegated_roles.find_keys_roles(delegated_role1_keys) == "delegated_role1"


def _load_roles_pub_key(keystore, key_name):
    key = import_rsa_publickey_from_file(
        str(Path(keystore) / f"{key_name}.pub")
    )
    return key