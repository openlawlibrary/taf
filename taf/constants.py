# Default scheme for all RSA keys. It can be changed in keys.json while
# generating repository
import datetime
from typing import List, Optional


DEFAULT_RSA_SIGNATURE_SCHEME = "rsa-pkcs1v15-sha256"

CAPSTONE = "capstone"


class RoleSetupParams:
    def __init__(
        self,
        number: int = 1,
        threshold: int = 1,
        yubikey: bool = False,
        scheme: str = DEFAULT_RSA_SIGNATURE_SCHEME,
        length: int = 3072,
        passwords: Optional[List[str]] = None,
        terminating: bool = True,
    ):
        self.number = number
        self.threshold = threshold
        self.yubikey = yubikey
        self.scheme = scheme
        self.length = length
        self.passwords = passwords
        self.terminating = terminating

    def __getitem__(self, key):
        return getattr(self, key, None)


DEFAULT_ROLE_SETUP_PARAMS = RoleSetupParams()

# Yubikey x509 certificate expiration interval
EXPIRATION_INTERVAL = 36500

YUBIKEY_EXPIRATION_DATE = datetime.datetime.now() + datetime.timedelta(
    days=EXPIRATION_INTERVAL
)
