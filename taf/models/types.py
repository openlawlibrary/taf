from typing import Optional
import attrs
from pathlib import Path

from taf.constants import DEFAULT_ROLE_SETUP_PARAMS
from taf.exceptions import RepositorySpecificationError
from taf.models.validators import (
    integer_validator,
    optional_type_validator,
    role_number_validator,
    role_paths_validator,
)


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


@attrs.define
class DelegatedRole(Role):
    name: Optional[str] = attrs.field(default=None, kw_only=True)
    paths: list[str] = attrs.field(kw_only=True, validator=role_paths_validator)
    terminating: Optional[bool] = attrs.field(
        validator=optional_type_validator(bool),
        default=DEFAULT_ROLE_SETUP_PARAMS["terminating"],
    )


class RootRole(Role):
    name: str = "root"


@attrs.define
class TargetsRole(Role):
    name: str = "targets"
    delegations: Optional[dict[str, DelegatedRole]] = attrs.field(kw_only=True)

    def __attrs_post_init__(self):
        if self.delegations:
            for role_name, delegated_role in self.delegations.items():
                delegated_role.name = role_name

    def roles_list(self):
        return self.delegations.values()


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

    def roles_list(self):
        return [self.root, self.targets, self.snapshot, self.timestamp]


@attrs.define
class RolesKeysData:
    roles: MainRoles
    keystore: Optional[str] = attrs.field(
        validator=attrs.validators.instance_of(str), default=None
    )
    yubikeys: Optional[dict[str, UserKeyData]] = attrs.field(default=None)

    @keystore.validator
    def check_keystore(instance, attribute, value):
        if not Path(value).resolve().exists():
            raise RepositorySpecificationError(f"{attribute.name} path does not exist")
