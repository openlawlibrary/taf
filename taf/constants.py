# Default scheme for all RSA keys. It can be changed in keys.json while
# generating repository
import datetime


DEFAULT_RSA_SIGNATURE_SCHEME = "rsa-pkcs1v15-sha256"

CAPSTONE = "capstone"

DEFAULT_ROLE_SETUP_PARAMS = {
    "number": 1,
    "threshold": 1,
    "yubikey": False,
    "scheme": DEFAULT_RSA_SIGNATURE_SCHEME,
    "length": 3072,
    "passwords": None,
    "terminating": True,
}

# Yubikey x509 certificate expiration interval
EXPIRATION_INTERVAL = 36500

YUBIKEY_EXPIRATION_DATE = datetime.datetime.now() + datetime.timedelta(
    days=EXPIRATION_INTERVAL
)
