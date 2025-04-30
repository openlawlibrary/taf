from __future__ import annotations
import json
from typing import Iterator, List, Optional, Dict
import attrs

from taf.constants import DEFAULT_ROLE_SETUP_PARAMS
from taf.exceptions import RolesKeyDataConversionError
from taf.models.validators import (
    filepath_validator,
    integer_validator,
    optional_type_validator,
    public_key_validator,
    role_number_validator,
    role_paths_validator,
)
from attrs import validators


@attrs.frozen
class Commitish:
    hash: str
    tag: Optional[str] = None

    @property
    def value(self) -> str:
        return self.tag if self.tag else self.hash

    @classmethod
    def from_hash(cls, hash: Optional[Commitish | str]):
        """
        Initialize cls from `hash`.
        If `hash` is already `Commitish`, returns self
        """
        if hash is None:
            return None
        if isinstance(hash, str):
            return cls(hash)  # type: ignore
        return hash  # type: ignore

    def __eq__(self, other):
        if other is None:
            return False
        if isinstance(other, str):
            other = Commitish(other)
        return self.value == other.value

    def __hash__(self):
        return self.value.__hash__()

    def __str__(self):
        return self.value

    def __repr__(self):
        return f'Commitish("{self.value}")'

    def to_json(self):
        """Serialize as a plain string instead of an object."""
        return json.dumps(str(self))


@attrs.define
class UserKeyData:
    public: Optional[str] = attrs.field(validator=public_key_validator, default=None)
    scheme: Optional[str] = attrs.field(
        validator=optional_type_validator(str),
        default=DEFAULT_ROLE_SETUP_PARAMS["scheme"],
    )
    present: bool = attrs.field(default=True)


@attrs.define
class Role:
    name: str = attrs.field(kw_only=True)
    threshold: int = attrs.field(
        validator=integer_validator, default=DEFAULT_ROLE_SETUP_PARAMS["threshold"]
    )
    scheme: Optional[str] = attrs.field(
        validator=optional_type_validator(str),
        default=DEFAULT_ROLE_SETUP_PARAMS["scheme"],
    )
    length: Optional[int] = attrs.field(
        validator=optional_type_validator(int),
        default=DEFAULT_ROLE_SETUP_PARAMS["length"],
    )
    yubikeys: Optional[List[str]] = attrs.field(default=None)
    number: int = attrs.field(validator=role_number_validator)
    # TODO remove after reworking add role/storing yubikey ids in the repo
    yubikey: Optional[bool] = attrs.field(default=None)

    @number.default  # type: ignore
    def _number_factory(self):
        return (
            len(self.yubikeys) if self.yubikeys else DEFAULT_ROLE_SETUP_PARAMS["number"]
        )

    @property
    def is_yubikey(self):
        return bool(
            self.yubikey is True or (self.yubikeys is not None and len(self.yubikeys))
        )

    @property
    def yubikey_ids(self):
        if not self.is_yubikey:
            return None
        return self.yubikeys


@attrs.define
class RootRole(Role):
    name: str = "root"


@attrs.define
class TargetsRole(Role):
    name: str = "targets"
    parent: Optional[Role] = attrs.field(default=None, kw_only=True)
    paths: Optional[List[str]] = attrs.field(
        kw_only=True, default=None, validator=role_paths_validator
    )
    terminating: Optional[bool] = attrs.field(
        validator=optional_type_validator(bool),
        default=DEFAULT_ROLE_SETUP_PARAMS["terminating"],
    )
    delegations: Optional[Dict[str, TargetsRole]] = attrs.field(
        kw_only=True,
        default={},
    )  # type: ignore

    def __attrs_post_init__(self):
        def _update_delegations(role):
            for role_name, delegated_role in role.delegations.items():
                delegated_role.name = role_name
                delegated_role.parent = role
                _update_delegations(delegated_role)

        if self.delegations:
            _update_delegations(self)


@attrs.define
class SnapshotRole(Role):
    name: str = "snapshot"


@attrs.define
class TimestampRole(Role):
    name: str = "timestamp"


@attrs.define
class MainRoles:
    root: RootRole
    targets: TargetsRole
    snapshot: SnapshotRole
    timestamp: TimestampRole


@attrs.define
class RolesKeysData:
    roles: MainRoles
    keystore: Optional[str] = attrs.field(validator=filepath_validator, default=None)  # type: ignore
    yubikeys: Optional[Dict[str, UserKeyData]] = attrs.field(default=None)

    def __attrs_post_init__(self):
        for role in RolesIterator(self.roles):
            if role.yubikeys:
                if not self.yubikeys:
                    raise RolesKeyDataConversionError(
                        exceptions=[
                            f"yubikeys of role {role.name} are listed, but yubikeys are not defined"
                        ]
                    )

                for key_id in role.yubikeys:
                    if key_id not in self.yubikeys:
                        raise RolesKeyDataConversionError(
                            exceptions=[
                                f"role {role.name} references yubikey {key_id}, but it is not specified"
                            ]
                        )


class RolesIterator:
    """
    Given an instance of MainRoles (which contains root, targets, snapshot or timestamp)
    or a targets (or delegated targets), iterate over all roles in the roles hierarchy.
    In case of MainRoles, iterate over root, targets, all delegated targets, snapshot and
    timestamp in that order. In case of a targets role, iterate over all of its nested
    targets roles
    """

    def __init__(
        self,
        roles: MainRoles | Role,
        include_delegations: Optional[bool] = True,
        skip_top_role: Optional[bool] = False,
    ):
        self.roles = roles
        self.include_delegations = include_delegations
        self.skip_top_role = skip_top_role

    def __iter__(self) -> Iterator:
        # Define the order of roles
        if isinstance(self.roles, MainRoles):
            roles = [
                self.roles.root,
                self.roles.targets,
                self.roles.snapshot,
                self.roles.timestamp,
            ]
        else:
            roles = [self.roles]

        def _dfs_delegations(role, skip_top_role=False):
            if not skip_top_role:
                yield role

            if self.include_delegations and hasattr(role, "delegations"):
                for delegation in role.delegations.values():
                    yield from _dfs_delegations(delegation)

        for role in roles:
            yield from _dfs_delegations(role, self.skip_top_role)


def compare_roles_data(old_data: RolesKeysData, new_data: RolesKeysData):
    added_roles = []
    removed_roles = []
    current_roles = {
        role.name: role
        for role in RolesIterator(old_data.roles.targets, skip_top_role=True)
    }
    new_roles = {
        role.name: role
        for role in RolesIterator(new_data.roles.targets, skip_top_role=True)
    }

    for role_name, role in current_roles.items():
        if role_name not in new_roles:
            removed_roles.append(role)

    for role_name, role in new_roles.items():
        if role_name not in current_roles:
            added_roles.append(role)

    return added_roles, removed_roles


@attrs.define(slots=True, frozen=True)
class KeyEntry:
    """
    Single entry inside keys-mapping.json.
    """

    public: str = attrs.field(validator=validators.instance_of(str))
    keyid: str = attrs.field(validator=validators.instance_of(str))
    scheme: str = attrs.field(validator=validators.instance_of(str))

    @staticmethod
    def from_dict(data: Dict[str, str]) -> "KeyEntry":
        """
        Parse one object (the value part in keys-mapping.json).
        """
        return KeyEntry(  # type: ignore[call-arg]
            public=data["public"],
            keyid=data["keyid"],
            scheme=data["scheme"],
        )


@attrs.define(slots=True, frozen=True)
class KeysMapping:
    """
    Wrapper around the whole keys-mapping.json file.
    Maps key-name -> KeyEntry.
    """

    entries: Dict[str, KeyEntry]

    @staticmethod
    def from_dict(mapping: Dict[str, Dict[str, str]]) -> "KeysMapping":
        return KeysMapping(  # type: ignore[call-arg]
            entries={name: KeyEntry.from_dict(info) for name, info in mapping.items()}
        )

    def find_name_by_public(self, public_pem: str) -> Optional[str]:
        for name, info in self.entries.items():
            if info.public == public_pem:
                return name
        return None

    def find_name_by_keyid(self, keyid: str) -> Optional[str]:
        for name, info in self.entries.items():
            if info.keyid == keyid:
                return name
        return None
