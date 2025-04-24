from __future__ import annotations
import attrs

from typing import Dict, Optional

from attrs import validators


@attrs.define(slots=True, frozen=True)
class KeyEntry:
    """
    Single entry inside keys-mapping.json.
    """

    public: str = attrs.field(validator=validators.instance_of(str))
    keyid: str = attrs.field(validator=validators.instance_of(str))
    scheme: str = attrs.field(validator=validators.instance_of(str))

    @staticmethod
    def from_dict(data: Dict[str, str]) -> "KeyEntry":
        """
        Parse one object (the value part in keys-mapping.json).
        """
        return KeyEntry(  # type: ignore[call-arg]
            public=data["public"],
            keyid=data["keyid"],
            scheme=data["scheme"],
        )


@attrs.define(slots=True, frozen=True)
class KeysMapping:
    """
    Wrapper around the whole keys-mapping.json file.
    Maps key-name -> KeyEntry.
    """

    entries: Dict[str, KeyEntry]

    @staticmethod
    def from_dict(mapping: Dict[str, Dict[str, str]]) -> "KeysMapping":
        return KeysMapping(  # type: ignore[call-arg]
            entries={name: KeyEntry.from_dict(info) for name, info in mapping.items()}
        )

    def find_name_by_public(self, public_pem: str) -> Optional[str]:
        for name, info in self.entries.items():
            if info.public == public_pem:
                return name
        return None
