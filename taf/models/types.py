from __future__ import annotations
import json
from typing import TYPE_CHECKING, Iterator, List, Optional, Dict
import attrs

if TYPE_CHECKING:
    import pygit2

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
    """
    A commit, identified by its hash and optionally by a tag.
    If a tag is set, it is used as the commit's value.

    >>> Commitish("abc123")
    Commitish("abc123")
    >>> Commitish("abc123", tag="v1.0").value
    'v1.0'

    Can be compared with a string and serialized as one:

    >>> Commitish("abc123") == "abc123"
    True
    >>> Commitish("abc123").to_json()
    '"abc123"'
    >>> Commitish.from_hash("abc123")
    Commitish("abc123")
    >>> Commitish.from_hash(None) is None
    True
    """

    hash: str
    tag: Optional[str] = None

    @property
    def value(self) -> str:
        return self.tag if self.tag else self.hash

    @classmethod
    def from_hash(cls, hash: Optional[Commitish | str | pygit2.Oid]):
        """
        Initialize cls from `hash`.
        If `hash` is already `Commitish`, returns self.
        A pygit2 Oid is converted through str(), which yields its hex digest
        on every pygit2 version TAF supports.
        """
        if hash is None:
            return None
        if isinstance(hash, Commitish):
            return hash
        return cls(str(hash))  # type: ignore

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
    """
    One entry of the `yubikeys` part of a keys description. All properties
    are optional.

    >>> from taf.models.converter import from_dict
    >>> from_dict({}, UserKeyData)
    UserKeyData(public=None, scheme='rsa-pkcs1v15-sha256', present=True)
    >>> from_dict({"public": "-----BEGIN PUBLIC KEY-----...", "present": False}, UserKeyData)
    UserKeyData(public='-----BEGIN PUBLIC KEY-----...', scheme='rsa-pkcs1v15-sha256', present=False)

    The public key has to be in the PEM format:

    >>> from_dict({"public": "not a key"}, UserKeyData)
    Traceback (most recent call last):
        ...
    taf.exceptions.RolesKeyDataConversionError: Public key must start with '-----BEGIN PUBLIC KEY-----'
    """

    public: Optional[str] = attrs.field(validator=public_key_validator, default=None)
    scheme: Optional[str] = attrs.field(
        validator=optional_type_validator(str),
        default=DEFAULT_ROLE_SETUP_PARAMS["scheme"],
    )
    present: bool = attrs.field(default=True)


@attrs.define
class Role:
    """
    Properties shared by all roles. A role of a keys description is one of
    the subclasses, which also set the role's name.

    >>> Role(name="my_role")
    Role(name='my_role', threshold=1, scheme='rsa-pkcs1v15-sha256', length=3072,
         yubikeys=None, number=1, yubikey=None)

    If `yubikeys` are listed, `number` is set to the number of listed YubiKeys:

    >>> role = Role(name="my_role", threshold=2, yubikeys=["user1", "user2"])
    >>> role.number
    2
    >>> role.is_yubikey
    True
    >>> role.yubikey_ids
    ['user1', 'user2']

    The number of keys cannot be lower than the threshold, and it has to match
    the number of listed YubiKeys:

    >>> Role(name="my_role", threshold=2)
    Traceback (most recent call last):
        ...
    ValueError: my_role definition error: number of signing keys (1) is lower than the threshold (2)
    >>> Role(name="my_role", number=3, yubikeys=["user1"])
    Traceback (most recent call last):
        ...
    ValueError: my_role definition error: number of signing keys (3) is not the same as the number of specified yubikeys. Omit the number property if specifying yubikeys or make sure these values match
    """

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
    """
    >>> from taf.models.converter import from_dict
    >>> from_dict({}, RootRole)
    RootRole(threshold=1, scheme='rsa-pkcs1v15-sha256', length=3072,
             yubikeys=None, number=1, yubikey=None, name='root')
    >>> from_dict({"number": 3, "threshold": 2, "length": 2048, "yubikey": True}, RootRole)
    RootRole(threshold=2, scheme='rsa-pkcs1v15-sha256', length=2048,
             yubikeys=None, number=3, yubikey=True, name='root')
    """

    name: str = "root"


@attrs.define
class TargetsRole(Role):
    """
    The targets role, or one of its delegated roles.

    >>> from taf.models.converter import from_dict
    >>> from_dict({}, TargetsRole)
    TargetsRole(threshold=1, scheme='rsa-pkcs1v15-sha256', length=3072,
                yubikeys=None, number=1, yubikey=None, name='targets',
                parent=None, paths=None, terminating=True, delegations={})

    Delegated roles are listed under `delegations`, by their names. Each of
    them gets its name and its parent set, and can have its own delegations:

    >>> targets = from_dict(
    ...     {
    ...         "delegations": {
    ...             "delegated_role": {
    ...                 "paths": ["dir1/*"],
    ...                 "threshold": 2,
    ...                 "number": 2,
    ...                 "terminating": False,
    ...                 "delegations": {"inner_role": {"paths": ["dir1/inner/*"]}},
    ...             }
    ...         }
    ...     },
    ...     TargetsRole,
    ... )
    >>> delegated_role = targets.delegations["delegated_role"]
    >>> delegated_role.name, delegated_role.parent.name
    ('delegated_role', 'targets')
    >>> delegated_role.paths, delegated_role.threshold, delegated_role.terminating
    (['dir1/*'], 2, False)
    >>> inner_role = delegated_role.delegations["inner_role"]
    >>> inner_role.name, inner_role.parent.name
    ('inner_role', 'delegated_role')

    Delegated paths are directory names or `*`, separated by `/`:

    >>> from_dict({"paths": ["<dir1>"]}, TargetsRole)
    Traceback (most recent call last):
        ...
    taf.exceptions.RolesKeyDataConversionError: <dir1> is not a valid delegated path. Delegated paths are valid directory names or * separated by /
    """

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
    """
    The `roles` part of a keys description. All four roles have to be listed,
    but their properties can be left out.

    >>> from taf.models.converter import from_dict
    >>> roles = from_dict(
    ...     {"root": {"number": 3, "threshold": 2}, "targets": {}, "snapshot": {}, "timestamp": {}},
    ...     MainRoles,
    ... )
    >>> roles.root.number, roles.root.threshold
    (3, 2)
    >>> roles.targets.number, roles.targets.threshold
    (1, 1)
    """

    root: RootRole
    targets: TargetsRole
    snapshot: SnapshotRole
    timestamp: TimestampRole


@attrs.define
class RolesKeysData:
    """
    The whole keys description - roles, and optionally the keystore location
    and the YubiKeys that the roles are signed with.

    >>> from taf.models.converter import from_dict
    >>> keys_description = {
    ...     "yubikeys": {
    ...         "user1": {"public": "-----BEGIN PUBLIC KEY-----..."},
    ...         "user2": {},
    ...     },
    ...     "roles": {
    ...         "root": {"threshold": 2, "yubikeys": ["user1", "user2"]},
    ...         "targets": {"delegations": {"delegated_role": {"paths": ["dir1/*"]}}},
    ...         "snapshot": {},
    ...         "timestamp": {},
    ...     },
    ...     "keystore": ".",
    ... }
    >>> roles_keys_data = from_dict(keys_description, RolesKeysData)
    >>> roles_keys_data.keystore
    '.'
    >>> sorted(roles_keys_data.yubikeys)
    ['user1', 'user2']
    >>> roles_keys_data.roles.root.number
    2
    >>> [role.name for role in RolesIterator(roles_keys_data.roles)]
    ['root', 'targets', 'delegated_role', 'snapshot', 'timestamp']

    YubiKeys listed by a role have to be defined under `yubikeys`:

    >>> del keys_description["yubikeys"]["user2"]
    >>> from_dict(keys_description, RolesKeysData)
    Traceback (most recent call last):
        ...
    taf.exceptions.RolesKeyDataConversionError: role root references yubikey user2, but it is not specified

    The keystore directory has to exist:

    >>> from_dict(
    ...     {
    ...         "roles": {"root": {}, "targets": {}, "snapshot": {}, "timestamp": {}},
    ...         "keystore": "no/such/directory",
    ...     },
    ...     RolesKeysData,
    ... )
    Traceback (most recent call last):
        ...
    taf.exceptions.RolesKeyDataConversionError: no/such/directory does not exist
    """

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

    >>> from taf.models.converter import from_dict
    >>> targets = from_dict(
    ...     {
    ...         "delegations": {
    ...             "delegated_role": {
    ...                 "paths": ["dir1/*"],
    ...                 "delegations": {"inner_role": {"paths": ["dir1/inner/*"]}},
    ...             }
    ...         }
    ...     },
    ...     TargetsRole,
    ... )
    >>> [role.name for role in RolesIterator(targets)]
    ['targets', 'delegated_role', 'inner_role']
    >>> [role.name for role in RolesIterator(targets, skip_top_role=True)]
    ['delegated_role', 'inner_role']
    >>> [role.name for role in RolesIterator(targets, include_delegations=False)]
    ['targets']
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

    >>> KeyEntry.from_dict(
    ...     {"public": "-----BEGIN PUBLIC KEY-----...", "keyid": "keyid1", "scheme": "rsa-pkcs1v15-sha256"}
    ... )
    KeyEntry(public='-----BEGIN PUBLIC KEY-----...', keyid='keyid1', scheme='rsa-pkcs1v15-sha256')
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

    >>> keys_mapping = KeysMapping.from_dict(
    ...     {
    ...         "user1": {
    ...             "public": "-----BEGIN PUBLIC KEY-----...",
    ...             "keyid": "keyid1",
    ...             "scheme": "rsa-pkcs1v15-sha256",
    ...         }
    ...     }
    ... )
    >>> keys_mapping.find_name_by_keyid("keyid1")
    'user1'
    >>> keys_mapping.find_name_by_public("-----BEGIN PUBLIC KEY-----...")
    'user1'
    >>> keys_mapping.find_name_by_keyid("keyid2") is None
    True
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
