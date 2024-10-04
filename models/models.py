from typing import Optional


class TAFKey:
    def __init__(
        self,
        key_id: str,
        name: Optional[str] = None,
        organization: Optional[str] = None,
        country: Optional[str] = None,
        state: Optional[str] = None,
        locality: Optional[str] = None,
        valid_from: Optional[str] = None,
        valid_to: Optional[str] = None,
    ):
        self.key_id = key_id
        self.name = name or ""
        self.organization = organization or ""
        self.country = country or ""
        self.state = state or ""
        self.locality = locality or ""
        self.valid_from = valid_from or ""
        self.valid_to = valid_to or ""

    def __str__(self):
        attributes = [
            f"Key ID: {self.key_id}",
            f"Name: {self.name}" if self.name else None,
            f"Organization: {self.organization}" if self.organization else None,
            f"Country: {self.country}" if self.country else None,
            f"State: {self.state}" if self.state else None,
            f"Locality: {self.locality}" if self.locality else None,
            f"Valid From: {self.valid_from}" if self.valid_from else None,
            f"Valid To: {self.valid_to}" if self.valid_to else None,
        ]

        return "\n".join(filter(None, attributes))
