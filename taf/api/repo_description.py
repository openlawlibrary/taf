import json
import attr
from pathvalidate import sanitize_filepath
from pathlib import Path


def check_additional_keys(model, data_dict):
    # Get the keys from the JSON data
    json_keys = set(data_dict.keys())

    # Define the expected keys in your model
    expected_keys = set(attr.fields_dict(model).keys())

    # Check if there are unexpected keys in the JSON data
    unexpected_keys = json_keys - expected_keys

    if unexpected_keys:
        raise ValueError(f"JSON data contains unexpected fields: {unexpected_keys}")


@attr.s(auto_attribs=True)
class UserKeyData:
    public: str = attr.field()
    scheme: str

    @public.validator
    def check_public(instance, attribute, value):
        if value is not None and not value.startswith("-----BEGIN PUBLIC KEY-----"):
            raise ValueError("Public key must start with '-----BEGIN PUBLIC KEY-----'")

    @classmethod
    def from_dict(cls, d) -> "UserKeyData":
        check_additional_keys(cls, d)
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

    @number.validator
    def check_number(self, attribute, value):
        if not isinstance(value, int) or value < 1:
            raise ValueError("number must be an integer greater than 1")

    @threshold.validator
    def check_threshold(self, attribute, value):
        if not isinstance(value, int):
            raise ValueError("threshold must be an integer greater than 1")

    @classmethod
    def from_dict(cls, d) -> "Role":
        check_additional_keys(cls, d)
        return cls(
            number=d.get("number", 1),
            threshold=d.get("threshold", 1),
            yubikeys=d.get("yubikeys", []),
            scheme=d.get("scheme"),
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
                raise ValueError(f"The path '{path}' is not a valid Unix path")

    @classmethod
    def from_dict(cls, d) -> "DelegatedRole":
        check_additional_keys(cls, d)
        return cls(
            number=d.get("number", 1),
            threshold=d.get("threshold", 1),
            yubikeys=d.get("yubikeys", []),
            scheme=d.get("scheme"),
            paths=d.get("paths", []),
            terminating=d.get("terminating"),
        )


@attr.s(auto_attribs=True)
class MainRoles:
    root: Role
    targets: Role
    snapshot: Role
    timestamp: Role

    @classmethod
    def from_dict(cls, d) -> "MainRoles":
        check_additional_keys(cls, d)
        return cls(
            root=Role.from_dict(d.get("root", {})),
            targets=TargetsRole.from_dict(d.get("targets", {})),
            snapshot=Role.from_dict(d.get("snapshot", {})),
            timestamp=Role.from_dict(d.get("timestamp", {})),
        )


@attr.s(auto_attribs=True)
class DelegatedRoles:
    roles: dict[str:DelegatedRole]

    @classmethod
    def from_dict(cls, d) -> "DelegatedRoles":
        return cls(
            roles={key: DelegatedRole.from_dict(value) for key, value in d.items()}
        )


@attr.s(auto_attribs=True)
class TargetsRole(Role):
    delegations: DelegatedRoles

    @classmethod
    def from_dict(cls, d) -> "TargetsRole":
        check_additional_keys(cls, d)
        # TODO "validate roles here"
        return cls(
            number=d.get("number", 1),
            threshold=d.get("threshold", 1),
            yubikeys=d.get("yubikeys", []),
            scheme=d.get("scheme"),
            delegations=DelegatedRoles.from_dict(
                d.get("delegations", {}).get("roles", {})
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
            raise ValueError(f"{attribute.name} path does not exist")

    @classmethod
    def from_dict(cls, d) -> "Data":
        check_additional_keys(cls, d)
        return cls(
            keystore=d["keystore"],
            yubikeys={
                key: UserKeyData.from_dict(value)
                for key, value in d.get("yubikeys", {}).items()
            },
            roles=MainRoles.from_dict(d.get("roles", {})),
        )


# Load the JSON file
with open("D:\\oll\\library\\oll-test-repos\\keys-description.json", "r") as file:
    data_dict = json.load(file)

# Validate the JSON data using the defined class
data = Data.from_dict(data_dict)
import pdb

pdb.set_trace()
print("JSON is valid!")
