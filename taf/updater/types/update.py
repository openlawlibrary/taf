from attrs import define, field
from typing import Dict


@define
class Update:
    changed: bool = field(default=False)
    event: str = field(default="")
    error_msg: str = field(default="")
    auth_repos: Dict = field(factory=dict)
    auth_repo_name: str = field(default="")
