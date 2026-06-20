"""Schema tests for ``config.toml`` parsing (``taf.config``).

The ``[root]`` table records the root authentication repository, which carries
significant trust. Declaring one must never be a precondition for unrelated
archive work, so ``[root]`` is optional; but when present it must name a repo.
The schema must also stay complete: keys that the archive tooling actually
writes (e.g. ``url``) must be modelled rather than silently dropped, and
unknown keys must fail loudly rather than vanish.
"""

import pytest

from taf.config import TafConfig
from taf.exceptions import InvalidConfigError


def test_root_table_is_optional():
    # Absent [root] and the empty table written by `initialize_archive` both
    # mean "no root configured".
    assert TafConfig.from_mapping({}).root is None
    assert TafConfig.from_mapping({"root": {}}).root is None


def test_present_root_requires_name_and_org():
    with pytest.raises(InvalidConfigError):
        TafConfig.from_mapping({"root": {"org": "some-org"}})  # missing name
    with pytest.raises(InvalidConfigError):
        TafConfig.from_mapping({"root": {"name": "some-repo"}})  # missing org


def test_real_world_root_shape_is_fully_modelled():
    # The shape written by `shallow_clone_archive`: shallow + root{url,name,org}.
    cfg = TafConfig.from_mapping(
        {
            "shallow": True,
            "root": {
                "url": "git@github.com:some-org/some-repo.git",
                "name": "some-repo",
                "org": "some-org",
            },
        }
    )
    assert cfg.is_shallow
    assert cfg.root.name == "some-repo"
    assert cfg.root.org == "some-org"
    assert cfg.root.url == "git@github.com:some-org/some-repo.git"
    assert cfg.root.hash is None


def test_unknown_keys_are_rejected():
    with pytest.raises(InvalidConfigError):
        TafConfig.from_mapping({"root": {"name": "r", "org": "o", "bogus": 1}})
    with pytest.raises(InvalidConfigError):
        TafConfig.from_mapping({"surprise": True})
