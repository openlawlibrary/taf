from __future__ import annotations
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


@attrs.define
class UserKeyData:
    public: Optional[str] = attrs.field(validator=public_key_validator, default=None)
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
    yubikeys: Optional[List[str]] = attrs.field(default=None)
    number: int = attrs.field(validator=role_number_validator)
    # TODO remove after reworking add role/storing yubikey ids in the repo
    yubikey: Optional[bool] = attrs.field(default=None)

    @number.default
    def _number_factory(self):
        return (
            len(self.yubikeys) if self.yubikeys else DEFAULT_ROLE_SETUP_PARAMS["number"]
        )

    @property
    def is_yubikey(self):
        return bool(
            self.yubikey is True or (self.yubikeys is not None and len(self.yubikeys))
        )


class RootRole(Role):
    name: str = "root"


@attrs.define
class DelegatedRole(Role):
    name: Optional[str] = attrs.field(default=None, kw_only=True)
    parent: Optional[Role] = attrs.field(default=None, kw_only=True)
    paths: List[str] = attrs.field(kw_only=True, validator=role_paths_validator)
    terminating: Optional[bool] = attrs.field(
        validator=optional_type_validator(bool),
        default=DEFAULT_ROLE_SETUP_PARAMS["terminating"],
    )
    delegations: Optional[Dict[str, DelegatedRole]] = attrs.field(
        kw_only=True, default={}
    )


@attrs.define
class TargetsRole(Role):
    name: str = "targets"
    delegations: Optional[Dict[str, DelegatedRole]] = attrs.field(
        kw_only=True, default={}
    )

    def __attrs_post_init__(self):
        def _update_delegations(role):
            for role_name, delegated_role in role.delegations.items():
                delegated_role.name = role_name
                delegated_role.parent = role
                _update_delegations(delegated_role)

        if self.delegations:
            _update_delegations(self)


class SnapshotRole(Role):
    name: str = "snapshot"


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
    keystore: Optional[str] = attrs.field(validator=filepath_validator, default=None)
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
        if hasattr(self.roles, "root"):
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
