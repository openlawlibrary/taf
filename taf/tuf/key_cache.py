"""Cache public key deserialization in securesystemslib.

``SSlibKey._crypto_key`` re-parses the public key on every signature
verification. A TAF update verifies the same handful of keys thousands of
times (once per metadata file per validated commit), so the parsing is
memoized here. securesystemslib's own method does the parsing, so every key
type it supports keeps working. The cache key is the SSlibKey itself and the
returned ``cryptography`` public key objects are immutable, so sharing them
between SSlibKey instances cannot change any verification outcome.
"""

from functools import lru_cache

from securesystemslib.signer import SSlibKey

from taf.log import taf_logger

_sslib_crypto_key = getattr(SSlibKey, "_crypto_key", None)


@lru_cache(maxsize=256)
def _load_crypto_key_cached(key: SSlibKey):
    return _sslib_crypto_key(key)  # type: ignore


def _cached_crypto_key(self):
    """Drop-in replacement for SSlibKey._crypto_key."""
    return _load_crypto_key_cached(self)


def enable_public_key_cache() -> None:
    # Called once, at import time, so the warning below cannot be repeated.
    if hasattr(SSlibKey, "_crypto_key"):
        SSlibKey._crypto_key = _cached_crypto_key  # type: ignore
    else:
        taf_logger.warning(
            "securesystemslib internals changed: SSlibKey._crypto_key not found, "
            "skipping public key cache"
        )
