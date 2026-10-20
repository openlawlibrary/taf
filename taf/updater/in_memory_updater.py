from typing import Dict
from urllib import parse

from tuf.ngclient.updater import Updater

from taf.exceptions import UpdateFailedError

for _method in ("_load_local_metadata", "_persist_metadata"):
    if not hasattr(Updater, _method):
        raise UpdateFailedError(
            f"python-tuf internals changed: Updater.{_method} no longer exists. "
            "InMemoryUpdater must be updated to match the installed tuf version."
        )


class InMemoryUpdater(Updater):
    """TUF Updater whose local *trusted* metadata cache is an in-memory dict.

    python-tuf keeps a "local metadata directory" holding the trusted metadata
    it has already verified (the trust anchor for the next run): on each
    refresh it loads the trusted root from there, fetches new
    timestamp/snapshot/targets from the remote, fully verifies them
    (signatures, version/rollback, hashes, expiry) against that trusted state,
    and persists the new trusted metadata back. It is *not* a cache of remote
    files taken on faith - it is the output of verification.

    TAF validates every commit, running one Updater per commit, so this
    trusted store is written and re-read thousands of times per update. We
    replace the on-disk directory with a dict (``GitUpdater.metadata_store``)
    that is handed to each successive Updater, so the trusted state carries
    forward exactly as it would on disk - only the storage medium changes, not
    what is verified. Each commit's metadata is still fetched fresh (from git,
    via ``GitUpdater``) and re-validated against the store on every refresh, so
    the fact that metadata changes between commits is precisely what gets
    checked.

    Only the two private load/persist methods are overridden; all verification
    runs through unmodified python-tuf. ``test_in_memory_updater`` covers the
    store mechanics and the private-API guard, and the full ``test_updater``
    suite exercises real clone/update validation through this path. In
    ``--strict`` mode the store is additionally cross-checked against the
    on-disk metadata at each commit (see ``_validate_metadata_on_disk``).
    """

    def __init__(self, metadata_store: Dict[str, bytes], *args, **kwargs):
        # must be set before super().__init__, which loads the trusted root
        self._metadata_store = metadata_store
        super().__init__(*args, **kwargs)

    def _load_local_metadata(self, rolename: str) -> bytes:
        try:
            return self._metadata_store[parse.quote(rolename, "")]
        except KeyError:
            # an OSError subclass, matching the contract of the overridden
            # method which raises it when the metadata file does not exist
            raise FileNotFoundError(rolename)

    def _persist_metadata(self, rolename: str, data: bytes) -> None:
        self._metadata_store[parse.quote(rolename, "")] = data
