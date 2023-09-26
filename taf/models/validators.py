import re
from pathlib import Path
import attrs
from typing import Any, List, Optional


def integer_validator(
    instance: Any,
    attribute: "attrs.Attribute[int]",
    value: Any,
) -> bool:
    """Validates that integer is a number >=1"""
    if not isinstance(value, int) or not (value >= 1):
        name = attribute.name if hasattr(attribute, "name") else str(attribute)
        raise ValueError(
            f"{instance.__class__.__qualname__}.{name} should be a number >= 1, but was {value}."
        )
    return True


def public_key_validator(
    instance: Any,
    attribute: "attrs.Attribute[str]",
    value: Any,
) -> bool:
    if value and not value.startswith("-----BEGIN PUBLIC KEY-----"):
        raise ValueError("Public key must start with '-----BEGIN PUBLIC KEY-----'")
    return True


def role_number_validator(
    instance: Any,
    attribute: "attrs.Attribute[int]",
    value: int,
) -> bool:

    prefix = f"{instance.name if hasattr(instance, 'name') else 'delegated role'} definition error:"
    if not isinstance(value, int) or value < 1:
        raise ValueError(f"{prefix} number must be an integer greater than 1")
    if value < instance.threshold:
        raise ValueError(
            f"{prefix} number of signing keys ({value}) is lower than the threshold ({instance.threshold})"
        )
    if (
        value is not None
        and instance.yubikeys is not None
        and len(instance.yubikeys)
        and value != len(instance.yubikeys)
    ):
        raise ValueError(
            f"{prefix} number of signing keys ({value}) is not the same as the number of specified yubikeys. "
            "Omit the number property if specifying yubikeys or make sure these values match"
        )
    return True


def role_paths_validator(
    instance: Any,
    attribute: "attrs.Attribute[List[str]]",
    value: Optional[List[str]],
) -> bool:
    if value is None:
        return False
    word_pattern = r"^[A-Za-z0-9_.-]*$"

    for path in value:
        words = path.split("/")

        for word in words:
            if not re.match(word_pattern, word) and word != "*":
                raise ValueError(
                    f"{path} is not a valid delegated path. Delegated paths are valid directory names or * separated by /"
                )

    return True


def filepath_validator(
    instance: Any,
    attribute: "attrs.Attribute[List[str]]",
    value: str,
) -> bool:
    if value is not None and not Path(value).resolve().exists():
        raise ValueError(f"{value} does not exist")
    return True


def optional_type_validator(type):
    return attrs.validators.optional(attrs.validators.instance_of(type))
