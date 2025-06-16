"""
config.py - Utility helpers for reading `config.toml` into an *immutable*
`TafConfig` instance

Quick start
-----------
from taf.config import load_config

cfg = load_config()
cfg = load_config("path/to/config.toml")

print(cfg.root.org)                     # -> "some-repo-law-org"
"""

from __future__ import annotations

import attrs
import tomli as toml  # type: ignore[import-untyped]
from pathlib import Path
from typing import Any, Mapping, Optional


@attrs.define(slots=True, frozen=True, kw_only=True)
class RootConfig:
    """Representation of the TOML `[root]` table."""

    name: str
    org: str
    hash: Optional[str]


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
        shallow = bool(mapping.get("shallow", False))

        root_tbl = mapping.get("root", {})
        root: Optional[RootConfig] = (
            RootConfig(  # type: ignore[call-arg]
                name=root_tbl["name"],
                org=root_tbl["org"],
                hash=root_tbl.get("hash"),
            )
            if root_tbl
            else None
        )

        return cls(shallow=shallow, root=root)  # type: ignore[call-arg]

    def to_mapping(self) -> dict[str, Any]:
        """Round-trip back to a JSON-serialisable mapping."""
        data: dict[str, Any] = {"shallow": self.shallow}
        if self.root:
            data["root"] = attrs.asdict(self.root)
        return data


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
