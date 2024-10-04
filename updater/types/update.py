import enum
from attrs import define, field
from typing import Dict


@define
class Update:
    changed: bool = field(default=False)
    event: str = field(default="")
    error_msg: str = field(default="")
    auth_repos: Dict = field(factory=dict)
    auth_repo_name: str = field(default="")


class UpdateType(enum.Enum):
    TEST = "test"
    OFFICIAL = "official"
    EITHER = "either"


class OperationType(enum.Enum):
    CLONE = 1
    UPDATE = 2
    CLONE_OR_UPDATE = 3
