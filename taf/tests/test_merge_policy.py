import json

import pytest

from taf.exceptions import InvalidConfigError
from taf.models.merge import (
    DEFAULT_POLICIES,
    MergePolicies,
    build_policy,
    resolve_policy,
)


def test_group_by_must_name_an_existing_group():
    with pytest.raises(InvalidConfigError):
        build_policy(
            branch_pattern=r"^update/(?P<role>\w+)\.\w+$", group_by="nonexistent"
        )


def test_group_by_matching_a_real_group_is_accepted():
    policy = build_policy(
        branch_pattern=r"^update/(?P<role>\w+)\.\w+$", group_by="role"
    )
    assert policy.group_by == "role"


def test_allow_uneven_branch_lengths_defaults_to_false():
    policy = build_policy(branch_pattern=r"^rdf/publication/.*$")
    assert policy.allow_uneven_branch_lengths is False


def test_allow_uneven_branch_lengths_kebab_case_key():
    policies = MergePolicies.from_mapping(
        {
            "policies": {
                "rdf": {
                    "branch-pattern": r"^rdf/publication/.*$",
                    "allow-uneven-branch-lengths": True,
                }
            }
        }
    )
    assert policies.resolve("rdf").allow_uneven_branch_lengths is True


def test_from_mapping_converts_kebab_case_keys():
    policies = MergePolicies.from_mapping(
        {
            "policies": {
                "speculative": {
                    "branch-pattern": r"^publication/.*$",
                    "gate": "codified-date",
                    "no-capstone-roles": ["docs", "assets"],
                }
            }
        }
    )
    policy = policies.resolve("speculative")
    assert policy.branch_pattern == r"^publication/.*$"
    assert policy.gate == "codified-date"
    assert policy.no_capstone_roles == ["docs", "assets"]


def test_resolve_falls_back_to_default_when_not_in_file():
    policies = MergePolicies.from_mapping({"policies": {}})
    assert policies.resolve("speculative") == DEFAULT_POLICIES["speculative"]


def test_resolve_unknown_policy_raises():
    policies = MergePolicies.from_mapping({"policies": {}})
    with pytest.raises(InvalidConfigError):
        policies.resolve("nonexistent")


def test_partner_override_replaces_only_named_fields():
    policies = MergePolicies.from_mapping(
        {
            "policies": {},
            "partners": {"DCCouncil/law": {"speculative": {"gate": None}}},
        }
    )
    policy = policies.resolve("speculative", partner_name="DCCouncil/law")
    assert policy.gate is None
    assert policy.branch_pattern == DEFAULT_POLICIES["speculative"].branch_pattern

    assert (
        policies.resolve("speculative", partner_name="other/law")
        == DEFAULT_POLICIES["speculative"]
    )


def test_resolve_policy_prefers_config_path_over_defaults(tmp_path):
    config_path = tmp_path / "merge-policies.json"
    config_path.write_text(
        json.dumps({"policies": {"speculative": {"branch-pattern": r"^custom/.*$"}}})
    )

    policy = resolve_policy("speculative", config_path=str(config_path))

    assert policy.branch_pattern == r"^custom/.*$"


def test_resolve_policy_uses_built_in_default_when_nothing_else_available():
    policy = resolve_policy("update")
    assert policy == DEFAULT_POLICIES["update"]


def test_resolve_policy_unknown_name_without_config_raises():
    with pytest.raises(InvalidConfigError):
        resolve_policy("nonexistent")
