import json
import attr
from pathvalidate import sanitize_filepath
from pathlib import Path

from taf.constants import DEFAULT_ROLE_SETUP_PARAMS
from taf.exceptions import RepositorySpecificationError


def _check_additional_keys(model, data_dict):
    # Get the keys from the JSON data
    json_keys = set(data_dict.keys())

    # Define the expected keys in your model
    expected_keys = set(attr.fields_dict(model).keys())

    # Check if there are unexpected keys in the JSON data
    unexpected_keys = json_keys - expected_keys

    if unexpected_keys:
        raise RepositorySpecificationError(
            f"JSON data contains unexpected fields: {unexpected_keys}"
        )


def _insert_name_to_dict(data_dict, name):
    data_dict["name"] = name
    return data_dict


@attr.s(auto_attribs=True)
class UserKeyData:
    public: str = attr.field()
    scheme: str

    @public.validator
    def check_public(instance, attribute, value):
        if value is not None and not value.startswith("-----BEGIN PUBLIC KEY-----"):
            raise RepositorySpecificationError(
                "Public key must start with '-----BEGIN PUBLIC KEY-----'"
            )

    @classmethod
    def from_dict(cls, d) -> "UserKeyData":
        _check_additional_keys(cls, d)
        return cls(
            public=d.get("public"),
            scheme=d.get("scheme"),
        )


@attr.s(auto_attribs=True)
class Role:
    number: int = attr.field()
    threshold: int = attr.field()
    yubikeys: list[str]
    scheme: str
    name: str

    @number.validator
    def check_number(self, attribute, value):
        if not isinstance(value, int) or value < 1:
            raise RepositorySpecificationError(
                f"Role {self.name} is not valid: number must be an integer greater than 1"
            )
        if value < self.threshold:
            raise RepositorySpecificationError(
                f"Role {self.name} is not valid: number of signing keys ({value}) is lower than the threshold ({self.threshold})"
            )
        if value is not None and len(self.yubikeys) and value != len(self.yubikeys):
            raise RepositorySpecificationError(
                f"Role {self.name} is not valid: number of signing keys ({value}) is not the same as the number of specified yubikeys. "
                "Omit the number property if specifying yubikeys or make sure these values match"
            )

    @threshold.validator
    def check_threshold(self, attribute, value):
        if not isinstance(value, int):
            raise RepositorySpecificationError(
                "threshold must be an integer greater than 1"
            )

    @classmethod
    def from_dict(cls, data_dict) -> "Role":
        _check_additional_keys(cls, data_dict)
        yubikeys = yubikeys = data_dict.get("yubikeys", [])
        return cls(
            number=data_dict.get(
                "number", len(yubikeys) or DEFAULT_ROLE_SETUP_PARAMS["number"]
            ),
            threshold=data_dict.get(
                "threshold", DEFAULT_ROLE_SETUP_PARAMS["threshold"]
            ),
            yubikeys=yubikeys,
            scheme=data_dict.get("scheme"),
            name=data_dict.get("name"),
        )


@attr.s(auto_attribs=True)
class DelegatedRole(Role):
    paths: list[str] = attr.field()
    terminating: bool

    @paths.validator
    def check_paths(self, attribute, value):
        for path in value:
            sanitized_path = sanitize_filepath(path)
            if sanitized_path != path:
                raise RepositorySpecificationError(
                    f"The path '{path}' is not a valid Unix path"
                )

    @classmethod
    def from_dict(cls, data_dict) -> "DelegatedRole":
        _check_additional_keys(cls, data_dict)
        yubikeys = yubikeys = data_dict.get("yubikeys", [])
        return cls(
            number=data_dict.get(
                "number", len(yubikeys) or DEFAULT_ROLE_SETUP_PARAMS["number"]
            ),
            threshold=data_dict.get(
                "threshold", DEFAULT_ROLE_SETUP_PARAMS["threshold"]
            ),
            yubikeys=yubikeys,
            scheme=data_dict.get("scheme"),
            name=data_dict.get("name"),
            paths=data_dict.get("paths", []),
            terminating=data_dict.get("terminating"),
        )


@attr.s(auto_attribs=True)
class MainRoles:
    root: Role
    targets: Role
    snapshot: Role
    timestamp: Role

    @classmethod
    def from_dict(cls, data_dict) -> "MainRoles":
        _check_additional_keys(cls, data_dict)
        return cls(
            root=Role.from_dict(
                _insert_name_to_dict(data_dict.get("root", {}), "root")
            ),
            targets=TargetsRole.from_dict(
                _insert_name_to_dict(data_dict.get("targets", {}), "targets")
            ),
            snapshot=Role.from_dict(
                _insert_name_to_dict(data_dict.get("snapshot", {}), "snapshot")
            ),
            timestamp=Role.from_dict(
                _insert_name_to_dict(data_dict.get("timestamp", {}), "timestamp")
            ),
        )


@attr.s(auto_attribs=True)
class DelegatedRoles:
    roles: dict[str:DelegatedRole]

    @classmethod
    def from_dict(cls, data_dict) -> "DelegatedRoles":
        return cls(
            roles={
                key: DelegatedRole.from_dict(_insert_name_to_dict(value, key))
                for key, value in data_dict.items()
            }
        )


@attr.s(auto_attribs=True)
class TargetsRole(Role):
    delegations: DelegatedRoles

    @classmethod
    def from_dict(cls, data_dict) -> "TargetsRole":
        _check_additional_keys(cls, data_dict)
        yubikeys = yubikeys = data_dict.get("yubikeys", [])
        return cls(
            number=data_dict.get(
                "number", len(yubikeys) or DEFAULT_ROLE_SETUP_PARAMS["number"]
            ),
            threshold=data_dict.get(
                "threshold", DEFAULT_ROLE_SETUP_PARAMS["threshold"]
            ),
            yubikeys=yubikeys,
            scheme=data_dict.get("scheme"),
            name=data_dict.get("name"),
            delegations=DelegatedRoles.from_dict(
                data_dict.get("delegations", {}).get("roles", {})
            ),
        )


@attr.s(auto_attribs=True)
class Data:
    keystore: str = attr.field()
    yubikeys: dict[str, UserKeyData]
    roles: MainRoles

    @keystore.validator
    def check_keystore(instance, attribute, value):
        if not Path(value).resolve().exists():
            raise RepositorySpecificationError(f"{attribute.name} path does not exist")

    @classmethod
    def from_dict(cls, data_dict) -> "Data":
        _check_additional_keys(cls, data_dict)
        return cls(
            keystore=data_dict.get("keystore"),
            yubikeys={
                key: UserKeyData.from_dict(value)
                for key, value in data_dict.get("yubikeys", {}).items()
            },
            roles=MainRoles.from_dict(data_dict.get("roles", {})),
        )


# Load the JSON file
with open("D:\\oll\\library\\oll-test-repos\\keys-description.json", "r") as file:
    data_dict = json.load(file)

# Validate the JSON data using the defined class
data = Data.from_dict(data_dict)
import pdb

pdb.set_trace()
print("JSON is valid!")
