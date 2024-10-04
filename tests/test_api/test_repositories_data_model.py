import pytest
from typing import Dict
from taf.exceptions import RolesKeyDataConversionError
from taf.models.converter import from_dict
from taf.models.types import RolesKeysData


def _check_yubikeys(roles_keys_data: RolesKeysData):
    assert roles_keys_data.yubikeys is not None
    assert len(roles_keys_data.yubikeys) == 3
    for key in ("user1", "user2", "userYK"):
        assert key in roles_keys_data.yubikeys
        assert roles_keys_data.yubikeys[key].scheme == "rsa-pkcs1v15-sha256"
    for key in ("user1", "user2"):
        public = roles_keys_data.yubikeys[key].public
        assert public is not None
        assert public.startswith("-----BEGIN PUBLIC KEY-----")


def _check_main_roles(roles_keys_data: RolesKeysData):

    assert roles_keys_data.roles.root.number == 3
    assert roles_keys_data.roles.root.threshold == 2
    assert roles_keys_data.roles.root.scheme == "rsa-pkcs1v15-sha256"

    assert roles_keys_data.roles.targets.number == 2
    assert roles_keys_data.roles.targets.threshold == 1
    assert roles_keys_data.roles.targets.scheme == "rsa-pkcs1v15-sha256"

    assert roles_keys_data.roles.snapshot.number == 1
    assert roles_keys_data.roles.snapshot.threshold == 1
    assert roles_keys_data.roles.snapshot.scheme == "rsa-pkcs1v15-sha256"
    assert roles_keys_data.roles.snapshot.is_yubikey is False

    assert roles_keys_data.roles.timestamp.number == 1
    assert roles_keys_data.roles.timestamp.threshold == 1
    assert roles_keys_data.roles.timestamp.scheme == "rsa-pkcs1v15-sha256"
    assert roles_keys_data.roles.timestamp.is_yubikey is False


def test_no_delegations(no_delegations_json_input: Dict):
    roles_keys_data = from_dict(no_delegations_json_input, RolesKeysData)
    assert roles_keys_data
    assert isinstance(roles_keys_data, RolesKeysData)
    _check_yubikeys(roles_keys_data)
    _check_main_roles(roles_keys_data)
    assert roles_keys_data.roles.root.yubikeys == ["user1", "user2", "userYK"]
    assert roles_keys_data.roles.root.is_yubikey is True
    assert roles_keys_data.roles.targets.yubikeys == ["user1", "user2"]
    assert roles_keys_data.roles.targets.is_yubikey is True
    assert roles_keys_data.roles.targets.delegations == {}


def test_no_yubikeys(no_yubikeys_json_input: Dict):
    roles_keys_data = from_dict(no_yubikeys_json_input, RolesKeysData)
    assert roles_keys_data
    assert isinstance(roles_keys_data, RolesKeysData)
    assert roles_keys_data.yubikeys is None
    _check_main_roles(roles_keys_data)
    assert roles_keys_data.roles.root.is_yubikey is False
    assert roles_keys_data.roles.targets.is_yubikey is False
    assert roles_keys_data.roles.targets.delegations == {}


def test_old_yubikey(with_old_yubikey_input: Dict):
    roles_keys_data = from_dict(with_old_yubikey_input, RolesKeysData)
    assert roles_keys_data
    assert isinstance(roles_keys_data, RolesKeysData)
    assert roles_keys_data.yubikeys is None
    _check_main_roles(roles_keys_data)
    assert roles_keys_data.roles.root.is_yubikey is True
    assert roles_keys_data.roles.targets.is_yubikey is True
    assert roles_keys_data.roles.targets.delegations == {}


def test_with_delegations_delegations(with_delegations_json_input: Dict):
    roles_keys_data = from_dict(with_delegations_json_input, RolesKeysData)
    assert roles_keys_data
    assert isinstance(roles_keys_data, RolesKeysData)
    _check_yubikeys(roles_keys_data)
    _check_main_roles(roles_keys_data)
    assert roles_keys_data.roles.root.yubikeys == ["user1", "user2", "userYK"]
    assert roles_keys_data.roles.root.is_yubikey is True
    assert roles_keys_data.roles.targets.yubikeys == ["user1", "user2"]
    assert roles_keys_data.roles.targets.is_yubikey is True
    assert roles_keys_data.roles.targets.delegations is not None
    assert len(roles_keys_data.roles.targets.delegations) == 1
    assert roles_keys_data.roles.targets.delegations is not None
    assert "delegated_role" in roles_keys_data.roles.targets.delegations
    assert roles_keys_data.roles.targets.delegations["delegated_role"].paths == [
        "dir1/*",
        "dir2/path1",
    ]
    assert roles_keys_data.roles.targets.delegations["delegated_role"].number == 2
    assert roles_keys_data.roles.targets.delegations["delegated_role"].threshold == 1
    assert roles_keys_data.roles.targets.delegations["delegated_role"].yubikeys == [
        "user1",
        "user2",
    ]
    assert (
        roles_keys_data.roles.targets.delegations["delegated_role"].delegations
        is not None
    )
    assert (
        len(roles_keys_data.roles.targets.delegations["delegated_role"].delegations)
        == 1
    )
    assert roles_keys_data.roles.targets.delegations["delegated_role"].delegations[
        "inner_role"
    ].paths == ["dir2/path2"]
    assert (
        roles_keys_data.roles.targets.delegations["delegated_role"]
        .delegations["inner_role"]
        .number
        == 2
    )
    assert (
        roles_keys_data.roles.targets.delegations["delegated_role"]
        .delegations["inner_role"]
        .threshold
        == 1
    )


def test_invalid_yubikeys(invalid_keys_number_json_input: Dict):
    with pytest.raises(RolesKeyDataConversionError) as error:
        from_dict(invalid_keys_number_json_input, RolesKeysData)
    assert (
        str(error.value)
        == "root definition error: number of signing keys (3) is not the same as the number of specified yubikeys. Omit the number property if specifying yubikeys or make sure these values match"
    )


def test_invalidkeys_number(invalid_public_key_json_input: Dict):
    with pytest.raises(RolesKeyDataConversionError) as error:
        from_dict(invalid_public_key_json_input, RolesKeysData)
    assert str(error.value) == "Public key must start with '-----BEGIN PUBLIC KEY-----'"


def test_invalid_path(invalid_path_input: Dict):
    with pytest.raises(RolesKeyDataConversionError) as error:
        from_dict(invalid_path_input, RolesKeysData)
    assert (
        str(error.value)
        == "dir1\\part1 is not a valid delegated path. Delegated paths are valid directory names or * separated by /"
    )
