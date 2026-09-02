"""
Merge policy configuration - the small amount of merge behaviour that is not
already carried in an authentication repository's signed target files
(destination branch, commit and any date gate are read from there; see
`taf.api.merge`). What is left - branch name patterns and capstone role
policy - lives here.

A policy file is signed JSON, normally at `targets/merge-policies.json` in a
root authentication repository shared by several partner repositories, so
changing it does not require re-signing every partner. Resolution order,
first hit wins: an explicit `--config` file, the root repository's signed
file, then the built-in defaults below.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional

import attrs
import cattrs

from taf.exceptions import InvalidConfigError


@attrs.define(slots=True, frozen=True, kw_only=True)
class MergePolicy:
    """
    One named merge policy.

    Attributes
    ----------
    branch_pattern
        Regular expression, with named capture groups, identifying and ordering
        source branches.
    group_by
        Name of a group in `branch_pattern` to select the newest branch per distinct
        value of (e.g. "role", for update branches with one branch family per role).
        If not given, the single newest matching branch is selected.
    gate
        Targets-metadata key holding an ISO date. Commits are merged up to the last one
        whose value for this key is today or earlier. If not given, all unmerged commits
        are merged.
    no_capstone_roles
        Roles exempt from the "branch ends with a capstone target file" check.
    check_branch_id_roles
        Roles whose branch ID should be validated across the whole branch.
    rename_merged
        Rename each merged branch to `merged/<branch>` and push the rename.
    set_default_branch
        If a repository's destination branch changed, set it as that repository's
        default branch on its git hosting provider.
    """

    branch_pattern: str
    group_by: Optional[str] = None
    gate: Optional[str] = None
    no_capstone_roles: List[str] = attrs.field(factory=list)
    check_branch_id_roles: List[str] = attrs.field(factory=list)
    rename_merged: bool = False
    set_default_branch: bool = False

    def __attrs_post_init__(self):
        if self.group_by and not _pattern_has_group(self.branch_pattern, self.group_by):
            raise InvalidConfigError(
                f"group-by '{self.group_by}' is not a named group in "
                f"branch-pattern '{self.branch_pattern}'"
            )


def _pattern_has_group(pattern: str, group: str) -> bool:
    return group in re.compile(pattern).groupindex


MERGE_POLICIES_TARGET_PATH = "merge-policies.json"

_converter = cattrs.Converter(forbid_extra_keys=False)


def _kebab_to_snake(data: Any) -> Any:
    if isinstance(data, dict):
        return {k.replace("-", "_"): _kebab_to_snake(v) for k, v in data.items()}
    if isinstance(data, list):
        return [_kebab_to_snake(v) for v in data]
    return data


def build_policy(**fields: Any) -> MergePolicy:
    """Build a `MergePolicy` from snake_case fields, e.g. `build_policy(branch_pattern=...)`."""
    try:
        return _converter.structure(fields, MergePolicy)
    except cattrs.ClassValidationError as e:
        cause = e.exceptions[0]
        if isinstance(cause, InvalidConfigError):
            raise cause from e
        raise


DEFAULT_POLICIES: Dict[str, MergePolicy] = {
    "speculative": build_policy(
        branch_pattern=(
            r"^publication/(?P<pub_date>\d{4}-\d{2}(-\d{2})?(-\d{2})?)"
            r"\.(?P<spec_date>\d{4}-\d{2}-\d{2}(-\d{2})?)$"
        ),
        gate="codified-date",
        no_capstone_roles=["docs", "assets"],
    ),
    "rdf": build_policy(
        branch_pattern=(
            r"^rdf/publication/(?P<pub_date>\d{4}-\d{2}(-\d{2})?(-\d{2})?)"
            r"\.(?P<spec_date>\d{4}-\d{2}-\d{2}(-\d{2})?)$"
        ),
        gate="codified-date",
    ),
    "update": build_policy(
        branch_pattern=r"^update/(?P<role>\w+)\.(?P<date>\d{4}-\d{2}-\d{2})(?P<idx>-\d{2})?$",
        group_by="role",
        rename_merged=True,
    ),
}


@attrs.define(slots=True, frozen=True, kw_only=True)
class MergePolicies:
    """In-memory representation of a `merge-policies.json` file."""

    policies: Dict[str, MergePolicy] = attrs.field(factory=dict)
    partners: Dict[str, Dict[str, Dict[str, Any]]] = attrs.field(factory=dict)

    @classmethod
    def from_mapping(cls, mapping: Mapping[str, Any]) -> "MergePolicies":
        try:
            return _converter.structure(_kebab_to_snake(dict(mapping)), cls)
        except cattrs.BaseValidationError as e:
            messages = "; ".join(str(sub) for sub in e.exceptions)
            raise InvalidConfigError(f"Invalid merge-policies.json: {messages}") from e

    def resolve(self, name: str, partner_name: Optional[str] = None) -> MergePolicy:
        base_policy = self.policies.get(name) or DEFAULT_POLICIES.get(name)
        if base_policy is None:
            raise InvalidConfigError(f"Unknown merge policy '{name}'")

        overrides = (
            self.partners.get(partner_name, {}).get(name) if partner_name else None
        )
        if not overrides:
            return base_policy
        return attrs.evolve(base_policy, **_kebab_to_snake(dict(overrides)))


def resolve_policy(
    name: str,
    config_path: Optional[str] = None,
    root_auth_repo: Optional[Any] = None,
    partner_name: Optional[str] = None,
) -> MergePolicy:
    """
    Resolve the merge policy named `name`, first hit wins:

    1. `config_path` - a local `merge-policies.json`-shaped file.
    2. `root_auth_repo`'s signed `targets/merge-policies.json`, if it has one.
    3. The built-in default for `name`.
    """
    if config_path is not None:
        data = json.loads(Path(config_path).read_text())
        return MergePolicies.from_mapping(data).resolve(name, partner_name)

    if root_auth_repo is not None:
        commit = root_auth_repo.head_commit()
        if commit is not None:
            raw = root_auth_repo.safely_get_json(
                commit, f"targets/{MERGE_POLICIES_TARGET_PATH}"
            )
            if raw is not None:
                return MergePolicies.from_mapping(raw).resolve(name, partner_name)

    if name not in DEFAULT_POLICIES:
        raise InvalidConfigError(
            f"Unknown merge policy '{name}' and no config was found to provide it"
        )
    return DEFAULT_POLICIES[name]


def locate_root_auth_repo(
    library_dir: Optional[str], root_auth_path: Optional[str] = None
):
    """
    Locate the root authentication repository, either at `root_auth_path`
    directly, or via the `[root]` table of `<library_dir>/.taf/config.toml`.
    Returns None if neither is available.
    """
    from taf.auth_repo import AuthenticationRepository
    from taf.config import load_config

    if root_auth_path is not None:
        return AuthenticationRepository(path=root_auth_path)

    if library_dir is None:
        return None

    config_toml = Path(library_dir, ".taf", "config.toml")
    if not config_toml.is_file():
        return None

    try:
        cfg = load_config(str(config_toml))
    except (FileNotFoundError, InvalidConfigError):
        return None
    if cfg.root is None:
        return None

    root_path = Path(library_dir, cfg.root.org, cfg.root.name)
    if not root_path.is_dir():
        return None
    return AuthenticationRepository(path=root_path)


def partner_name(auth_repo) -> Optional[str]:
    """Return `<namespace>/<name>` for `auth_repo`, from its signed info.json, if set."""
    info = auth_repo.get_info_json()
    if not info:
        return None
    namespace = info.get("namespace")
    name = info.get("name")
    if namespace is None or name is None:
        return None
    return f"{namespace}/{name}"
