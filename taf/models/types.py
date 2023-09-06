from __future__ import annotations
import json
from typing import Optional
import attrs
from pathlib import Path

from taf.constants import DEFAULT_ROLE_SETUP_PARAMS
from taf.models.iterators import RolesIterator
from taf.models.validators import (
    filepath_validator,
    integer_validator,
    optional_type_validator,
    role_number_validator,
    role_paths_validator,
)


class IterableRoles:
    def roles_list(self):
        raise NotImplementedError


@attrs.define
class UserKeyData:
    public: Optional[str] = attrs.field(
        validator=optional_type_validator(str), default=None
    )
    scheme: Optional[str] = attrs.field(
        validator=optional_type_validator(str),
        default=DEFAULT_ROLE_SETUP_PARAMS["scheme"],
    )


@attrs.define
class Role:
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
    yubikeys: Optional[list[str]] = attrs.field(default=None)
    number: int = attrs.field(validator=role_number_validator)

    @number.default
    def _number_factory(self):
        return (
            len(self.yubikeys) if self.yubikeys else DEFAULT_ROLE_SETUP_PARAMS["number"]
        )


class RootRole(Role):
    name: str = "root"


@attrs.define
class DelegatedRole(Role):
    name: Optional[str] = attrs.field(default=None, kw_only=True)
    paths: list[str] = attrs.field(kw_only=True, validator=role_paths_validator)
    terminating: Optional[bool] = attrs.field(
        validator=optional_type_validator(bool),
        default=DEFAULT_ROLE_SETUP_PARAMS["terminating"],
    )
    delegations: Optional[dict[str, DelegatedRole]] = attrs.field(
        kw_only=True, default={}
    )


@attrs.define
class TargetsRole(Role, IterableRoles):
    name: str = "targets"
    delegations: Optional[dict[str, DelegatedRole]] = attrs.field(
        kw_only=True, default={}
    )

    def __attrs_post_init__(self):
        if self.delegations:
            for role_name, delegated_role in self.delegations.items():
                delegated_role.name = role_name


class SnapshotRole(Role):
    name: str = "snapshot"


class TimestampRole(Role):
    name: str = "timestamp"


@attrs.define
class MainRoles(IterableRoles):
    root: RootRole
    targets: TargetsRole
    snapshot: SnapshotRole
    timestamp: TimestampRole


@attrs.define
class RolesKeysData:
    roles: MainRoles
    keystore: Optional[str] = attrs.field(validator=filepath_validator, default=None)
    yubikeys: Optional[dict[str, UserKeyData]] = attrs.field(default=None)

    def __attrs_post_init__(self):
        for role in RolesIterator(self.roles):
            if role.yubikeys:
                if not self.yubikeys:
                    raise ValueError(
                        f"yubikeys of role {role.name} are listed, but yubikeys are not defined"
                    )

                for key_id in role.yubikeys:
                    if key_id not in self.yubikeys:
                        raise ValueError(
                            f"role {role.name} references yubikey {key_id}, but it is not specified"
                        )
