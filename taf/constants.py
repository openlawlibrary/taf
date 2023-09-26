# Default scheme for all RSA keys. It can be changed in keys.json while
# generating repository
import datetime
from typing import List, Optional

import attrs


DEFAULT_RSA_SIGNATURE_SCHEME = "rsa-pkcs1v15-sha256"

CAPSTONE = "capstone"


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
