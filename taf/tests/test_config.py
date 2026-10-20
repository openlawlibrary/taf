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


def test_unknown_keys_in_root_are_rejected():
    # `root` is the one object taf depends on, so typos/extra keys there fail
    # loudly rather than being silently ignored.
    with pytest.raises(InvalidConfigError):
        TafConfig.from_mapping({"root": {"name": "r", "org": "o", "bogus": 1}})


def test_unknown_top_level_keys_are_tolerated():
    # The top level is co-owned by stelae, which writes tables taf does not
    # consume (e.g. [headers]). Unknown top-level keys must not break taf.
    cfg = TafConfig.from_mapping(
        {
            "root": {"name": "r", "org": "o"},
            "headers": {"current_documents_guard": "secret"},
            "some_future_table": {"anything": 1},
        }
    )
    assert cfg.root.name == "r"


def test_headers_contents_are_not_validated():
    # taf has nothing to say about the shape of [headers]; any contents load.
    cfg = TafConfig.from_mapping(
        {"root": {"name": "r", "org": "o"}, "headers": {"wholly": ["un", "modelled"]}}
    )
    assert cfg.root.org == "o"
