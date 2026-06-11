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
    """TUF Updater whose local metadata cache is an in-memory dict.

    TAF runs one Updater per validated commit, so the "local metadata
    directory" is written and re-read thousands of times per update. Keeping
    that cache in a dict (shared between successive Updater instances via
    GitUpdater.metadata_store) removes all of that disk I/O. Only the
    load/persist methods are overridden - every verification step still runs
    through unmodified python-tuf code.
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
