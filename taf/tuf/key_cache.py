"""Cache public key deserialization in securesystemslib.

``SSlibKey._crypto_key`` re-parses the public key on every signature
verification. A TAF update verifies the same handful of keys thousands of
times (once per metadata file per validated commit), so the parsing is
memoized here. securesystemslib's own method does the parsing, so every key
type it supports keeps working. The cache key is the key type and public key
value, and the returned ``cryptography`` public key objects are immutable, so
sharing them between SSlibKey instances cannot change any verification outcome.
"""

from typing import Any, Callable, Dict, Optional, Tuple

from securesystemslib.signer import SSlibKey

from taf.log import taf_logger

_original_crypto_key: Optional[Callable] = None
_crypto_keys: Dict[Tuple[str, str], Any] = {}


def _cached_crypto_key(self):
    """Drop-in replacement for SSlibKey._crypto_key."""
    cache_key = (self.keytype, self.keyval["public"])
    if cache_key not in _crypto_keys:
        _crypto_keys[cache_key] = _original_crypto_key(self)  # type: ignore
    return _crypto_keys[cache_key]


def enable_public_key_cache() -> None:
    global _original_crypto_key
    # Called once, at import time, so the warning below cannot be repeated.
    if not hasattr(SSlibKey, "_crypto_key"):
        taf_logger.warning(
            "securesystemslib internals changed: SSlibKey._crypto_key not found, "
            "skipping public key cache"
        )
    elif _original_crypto_key is None:
        _original_crypto_key = SSlibKey._crypto_key
        SSlibKey._crypto_key = _cached_crypto_key  # type: ignore
