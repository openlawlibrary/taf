import inspect

import pytest
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.primitives import hashes, serialization
from securesystemslib.exceptions import UnverifiedSignatureError
from securesystemslib.signer import SSlibKey, Signature
from tuf.api.exceptions import DownloadLengthMismatchError
from tuf.ngclient.updater import Updater

from taf.tuf.key_cache import _load_pem_public_key_cached
from taf.updater.handlers import GitUpdater
from taf.updater.in_memory_updater import InMemoryUpdater


def test_tuf_private_api_is_unchanged():
    """InMemoryUpdater overrides these private python-tuf methods, so fail
    loudly if a tuf upgrade changes their signatures."""
    load_params = list(inspect.signature(Updater._load_local_metadata).parameters)
    assert load_params == ["self", "rolename"]
    persist_params = list(inspect.signature(Updater._persist_metadata).parameters)
    assert persist_params == ["self", "rolename", "data"]


def test_in_memory_updater_load_and_persist():
    store = {}
    # bypass __init__ - only the storage overrides are under test here
    updater = InMemoryUpdater.__new__(InMemoryUpdater)
    updater._metadata_store = store

    updater._persist_metadata("targets", b"targets-data")
    assert updater._load_local_metadata("targets") == b"targets-data"
    # rolenames are quoted the same way tuf quotes local file names
    updater._persist_metadata("role/with/separators", b"delegated-data")
    assert store["role%2Fwith%2Fseparators"] == b"delegated-data"
    assert updater._load_local_metadata("role/with/separators") == b"delegated-data"

    # missing metadata must raise an OSError, like the file-based original
    with pytest.raises(OSError):
        updater._load_local_metadata("snapshot")


def test_metadata_store_key():
    assert GitUpdater._metadata_store_key("root.json") == "root"
    assert GitUpdater._metadata_store_key("targets.json") == "targets"
    # keys match what InMemoryUpdater computes from the rolename
    updater = InMemoryUpdater.__new__(InMemoryUpdater)
    updater._metadata_store = {GitUpdater._metadata_store_key("root.json"): b"data"}
    assert updater._load_local_metadata("root") == b"data"


class _FetcherStub:
    """Minimal object exposing fetch() the way FetcherInterface does."""

    def __init__(self, data):
        self._data = data

    def fetch(self, url):
        return iter([self._data])

    download_bytes = GitUpdater.download_bytes


def test_download_bytes_returns_data():
    fetcher = _FetcherStub(b"x" * 100)
    assert fetcher.download_bytes("metadata/root.json", 100) == b"x" * 100


def test_download_bytes_enforces_max_length():
    fetcher = _FetcherStub(b"x" * 101)
    with pytest.raises(DownloadLengthMismatchError):
        fetcher.download_bytes("metadata/root.json", 100)


@pytest.fixture
def rsa_key_pair():
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_pem = (
        private_key.public_key()
        .public_bytes(
            serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        .decode("utf-8")
    )
    return private_key, public_pem


def test_cached_key_verifies_and_rejects_signatures(rsa_key_pair):
    """The PEM-parse cache must not change any verification outcome."""
    private_key, public_pem = rsa_key_pair
    sslib_key = SSlibKey(
        "test-keyid",
        "rsa",
        "rsassa-pss-sha256",
        {"public": public_pem},
    )
    data = b"signed payload"
    signature_bytes = private_key.sign(
        data,
        padding.PSS(
            mgf=padding.MGF1(hashes.SHA256()), salt_length=hashes.SHA256().digest_size
        ),
        hashes.SHA256(),
    )
    signature = Signature("test-keyid", signature_bytes.hex())

    # verify twice so the second call exercises the cache hit
    sslib_key.verify_signature(signature, data)
    sslib_key.verify_signature(signature, data)

    with pytest.raises(UnverifiedSignatureError):
        sslib_key.verify_signature(signature, b"tampered payload")

    # the cache returns the same parsed key object for the same PEM
    assert _load_pem_public_key_cached(public_pem) is _load_pem_public_key_cached(
        public_pem
    )
