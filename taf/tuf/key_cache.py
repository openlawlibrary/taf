"""Cache PEM public key deserialization in securesystemslib.

``SSlibKey._crypto_key`` re-parses the PEM-encoded public key on every
signature verification. A TAF update verifies the same handful of keys
thousands of times (once per metadata file per validated commit), so the
parsing is memoized here. The cache key is the PEM string itself and the
returned ``cryptography`` public key objects are immutable, so sharing them
between SSlibKey instances cannot change any verification outcome.
"""

from functools import lru_cache

from cryptography.hazmat.primitives.serialization import load_pem_public_key
from securesystemslib.signer import SSlibKey

from taf.log import taf_logger


@lru_cache(maxsize=256)
def _load_pem_public_key_cached(public_pem: str):
    return load_pem_public_key(public_pem.encode("utf-8"))


def _cached_crypto_key(self):
    """Drop-in replacement for SSlibKey._crypto_key."""
    return _load_pem_public_key_cached(self.keyval["public"])


def enable_public_key_cache() -> None:
    if hasattr(SSlibKey, "_crypto_key"):
        SSlibKey._crypto_key = _cached_crypto_key  # type: ignore
    else:
        taf_logger.debug(
            "securesystemslib internals changed: SSlibKey._crypto_key not found, "
            "skipping public key cache"
        )
