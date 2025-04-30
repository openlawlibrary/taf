import attrs
import datetime
from typing import List, Optional


TARGETS_DIRECTORY_NAME = "targets"
METADATA_DIRECTORY_NAME = "metadata"


DEFAULT_RSA_SIGNATURE_SCHEME = "rsa-pkcs1v15-sha256"

CAPSTONE = "capstone"
PROTECTED_DIRECTORY_NAME = "protected"
INFO_JSON_PATH = f"{TARGETS_DIRECTORY_NAME}/{PROTECTED_DIRECTORY_NAME}/info.json"
KEYS_MAPPING_PATH = f"{TARGETS_DIRECTORY_NAME}/keys-mapping.json"


@attrs.define
class RoleSetupParams:
    number: int = attrs.field(default=1)
    threshold: int = attrs.field(default=1)
    yubikey: bool = attrs.field(default=False)
    scheme: str = attrs.field(default=DEFAULT_RSA_SIGNATURE_SCHEME)
    length: int = attrs.field(default=3072)
    passwords: Optional[List[str]] = attrs.field(default=None)
    terminating: bool = attrs.field(default=True)

    def __getitem__(self, key):
        return getattr(self, key, None)


DEFAULT_ROLE_SETUP_PARAMS = RoleSetupParams()

# Yubikey x509 certificate expiration interval
EXPIRATION_INTERVAL = 36500

YUBIKEY_EXPIRATION_DATE = datetime.datetime.now() + datetime.timedelta(
    days=EXPIRATION_INTERVAL
)
