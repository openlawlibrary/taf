"""
config.py - Utility helpers for reading `config.toml` into an *immutable*
`TafConfig` instance

Quick start
-----------
from taf.config import load_config

cfg = load_config()
cfg = load_config("path/to/config.toml")

print(cfg.root.name)                    # -> "some-repo-law"
"""

from __future__ import annotations

import attrs
import cattrs
import tomli as toml  # type: ignore[import-untyped]
from cattrs.gen import make_dict_structure_fn
from pathlib import Path
from typing import Any, Mapping, Optional

from taf.exceptions import InvalidConfigError


@attrs.define(slots=True, frozen=True, kw_only=True)
class RootConfig:
    """Representation of the TOML `[root]` table.

    The `[root]` table is optional: a root auth repo carries significant trust,
    so declaring one must never be a precondition for unrelated archive work.
    When the table *is* present it identifies the root authentication repo, so
    `name` and `org` are required.

    `url` and `hash` are optional records: the archive tooling writes `url`
    (the root repository's clone URL) but nothing reads it back, and `hash` is
    not written by any current producer. They are modelled so the schema stays
    complete rather than silently dropping keys that exist on disk.
    """

    name: str
    org: str
    url: Optional[str] = None
    hash: Optional[str] = None


@attrs.define(slots=True, frozen=True, kw_only=True)
class TafConfig:
    """
    Immutable in-memory representation of `config.toml`.

    Attributes
    ----------
    shallow
        Whether repository is shallow (top-level `shallow = true/false`).
    root
        Nested `[root]` table or *None* if omitted.
    """

    shallow: bool = False
    root: Optional[RootConfig] = None

    @property
    def is_shallow(self) -> bool:
        """Alias for the top-level *shallow* flag (reads nicer as a predicate)."""
        return self.shallow

    @classmethod
    def from_mapping(cls, mapping: Mapping[str, Any]) -> "TafConfig":
        # Treat an absent or empty `[root]` table as "no root configured" so
        # that unrelated commands never depend on a root repo being declared.
        data = dict(mapping)
        if not data.get("root"):
            data.pop("root", None)
        try:
            return _converter.structure(data, cls)
        except cattrs.BaseValidationError as e:
            messages = "; ".join(_iter_error_messages(e))
            raise InvalidConfigError(
                f"Invalid config.toml: {messages}"
            ) from e

    def to_mapping(self) -> dict[str, Any]:
        """Round-trip back to a JSON-serialisable mapping."""
        data: dict[str, Any] = {"shallow": self.shallow}
        if self.root:
            # Drop unset optionals: ``None`` is not TOML-serialisable.
            data["root"] = {
                k: v for k, v in attrs.asdict(self.root).items() if v is not None
            }
        return data


# Leniency is per-object on purpose:
#   * Top level is permissive. It is co-owned with the archive tooling, which
#     writes tables taf does not consume (e.g. [headers]); unknown top-level
#     keys are ignored so an evolving archive schema never breaks taf.
#   * `[root]` is strict. It is the one object taf actually depends on, so an
#     extra/typo'd key there fails loudly rather than silently dropping.
#   * [headers] (and any other table taf doesn't model) is opaque: taf has
#     nothing to say about its shape, and the lenient top level ignores it.
_converter = cattrs.Converter(forbid_extra_keys=False)
_converter.register_structure_hook(
    RootConfig,
    make_dict_structure_fn(
        RootConfig, _converter, _cattrs_forbid_extra_keys=True
    ),
)


def _iter_error_messages(exc: BaseException) -> list[str]:
    """Flatten cattrs' (possibly nested) validation errors into plain strings."""
    sub_exceptions = getattr(exc, "exceptions", None)
    if sub_exceptions:
        messages: list[str] = []
        for sub in sub_exceptions:
            messages.extend(_iter_error_messages(sub))
        return messages

    # A missing required field surfaces as a KeyError whose only payload is the
    # key name; turn it into something a user can act on.
    if isinstance(exc, KeyError) and exc.args:
        return [f"missing required key '{exc.args[0]}'"]
    return [str(exc)]


def load_config(config_path: str | Path | None = None) -> TafConfig:
    """
    Load *config.toml* and return a `TafConfig` instance.

    Parameters
    ----------
    config_path
        Explicit path to a TOML file.  If *None*, falls back to
        `find_taf_directory() ` / `config.toml`.

    Raises
    ------
    FileNotFoundError
        When the file cannot be found.
    KeyError
        When required TOML keys are missing.
    """
    from taf.api.utils._conf import find_taf_directory  # lazy import to avoid cycles

    base = find_taf_directory(Path.cwd())
    if base is None:
        raise FileNotFoundError("TAF directory not found")

    if config_path is None:
        candidate = base / "config.toml"
    else:
        candidate = Path(config_path).expanduser().resolve()

    if not candidate.is_file():
        raise FileNotFoundError(f"config.toml not found at: {candidate}")

    with candidate.open("rb") as fp:
        data = toml.load(fp)

    return TafConfig.from_mapping(data)
