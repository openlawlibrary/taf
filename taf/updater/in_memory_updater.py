import datetime
from typing import Dict, Set
from urllib import parse

from tuf.api.metadata import Targets
from tuf.ngclient.updater import Updater

from taf.exceptions import UpdateFailedError

for _method in ("_load_local_metadata", "_persist_metadata", "_load_targets"):
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

    def __init__(
        self,
        metadata_store: Dict[str, bytes],
        *args,
        check_expiration: bool = True,
        **kwargs,
    ):
        # must be set before super().__init__, which loads the trusted root
        self._metadata_store = metadata_store
        super().__init__(*args, **kwargs)
        if not check_expiration:
            # older commits' metadata may have expired since
            self._trusted_set.reference_time = datetime.datetime.min.replace(
                tzinfo=datetime.timezone.utc
            )

    def _load_local_metadata(self, rolename: str) -> bytes:
        try:
            return self._metadata_store[parse.quote(rolename, "")]
        except KeyError:
            # an OSError subclass, matching the contract of the overridden
            # method which raises it when the metadata file does not exist
            raise FileNotFoundError(rolename)

    def _persist_metadata(self, rolename: str, data: bytes) -> None:
        self._metadata_store[parse.quote(rolename, "")] = data

    def load_all_targets_roles(self) -> None:
        """Load and verify every delegated targets role, following the delegations
        of the roles that are already verified. TUF only loads the roles it needs
        to find a target file, so a role with no target files would otherwise
        not be checked."""
        roles_to_visit = [Targets.type]
        visited = set()
        while roles_to_visit:
            delegator = roles_to_visit.pop()
            if delegator in visited:
                continue
            visited.add(delegator)
            delegations = self._trusted_set[delegator].delegations
            if delegations is None or delegations.roles is None:
                continue
            for role in delegations.roles:
                self._load_targets(role, delegator)
                roles_to_visit.append(role)

    def signed_target_paths(self) -> Set[str]:
        """Paths of the target files listed by the targets roles verified so far."""
        return {
            target_path
            for signed in self._trusted_set
            if isinstance(signed, Targets)
            for target_path in signed.targets
        }
