"""TUF metadata repository"""


from pathlib import Path
import logging
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Dict, List

from securesystemslib.signer import Signer, Key

from tuf.api.metadata import (
    Metadata,
    MetaFile,
    Root,
    Snapshot,
    Targets,
    TargetFile,
    Timestamp,
)
from tuf.repository import Repository

logger = logging.getLogger(__name__)

METADATA_DIRECTORY_NAME = "metadata"


class MetadataRepository(Repository):
    """TUF metadata repository implementation for on-disk top-level roles.

    Provides methods to read and edit metadata, handling version and expiry
    bumps, and signature creation, and facilitating snapshot and timestamp
    creation.

    Arguments:
        path: Base path of metadata repository.

    Attributes:
        signer_cache: All signers available to the repository. Keys are role
            names, values are lists of signers. On `close` each signer for a
            role is used to sign the related role metadata.
    """

    expiry_period = timedelta(days=1)

    def __init__(self, path: Path) -> None:
        self.signer_cache: Dict[str, List[Signer]] = defaultdict(list)
        self._path = path

        self._snapshot_info = MetaFile(1)
        self._targets_infos: Dict[str, MetaFile] = defaultdict(lambda: MetaFile(1))

    @property
    def metadata_path(self) -> Path:
        return self._path / METADATA_DIRECTORY_NAME

    @property
    def targets_infos(self) -> Dict[str, MetaFile]:
        # tracks targets and root metadata changes, needed in `do_snapshot`
        return self._targets_infos

    @property
    def snapshot_info(self) -> MetaFile:
        # tracks snapshot metadata changes, needed in `do_timestamp`
        return self._snapshot_info

    def open(self, role: str) -> Metadata:
        """Read role metadata from disk."""
        return Metadata.from_file(self.metadata_path / f"{role}.json")

    def close(self, role: str, md: Metadata) -> None:
        """Bump version and expiry, re-sign, and write role metadata to disk."""
        md.signed.version += 1
        md.signed.expires = datetime.now(timezone.utc) + self.expiry_period

        md.signatures.clear()
        for signer in self.signer_cache[role]:
            md.sign(signer, append=True)

        fname = f"{role}.json"

        # Track snapshot, targets and root metadata changes, needed in
        # `do_snapshot` and `do_timestamp`
        if role == "snapshot":
            self._snapshot_info.version = md.signed.version
        elif role != "timestamp":  # role in [root, targets, <delegated targets>]
            self._targets_infos[fname].version = md.signed.version

        # Write role metadata to disk (root gets a version-prefixed copy)
        md.to_file(self.metadata_path / fname)
        if role == "root":
            md.to_file(self.metadata_path / f"{md.signed.version}.{fname}")

    def create(self):
        """Create a new metadata repository on disk.

        1. Create metadata subdir (fail, if exists)
        2. Create initial versions of top-level metadata
        3. Perform top-level delegation using keys from signer_cache.

        """
        self.metadata_path.mkdir()

        root = Root(consistent_snapshot=False)
        for role in ["root", "timestamp", "snapshot", "targets"]:
            for signer in self.signer_cache[role]:
                root.add_key(signer.public_key, role)

        # Snapshot tracks targets and root versions. targets v1 is included by
        # default in snapshot v1. root must be added explicitly.
        sn = Snapshot()
        sn.meta["root.json"] = MetaFile(1)

        for signed in [root, Timestamp(), sn, Targets()]:
            # Setting the version to 0 here is a trick, so that `close` can
            # always bump by the version 1, even for the first time
            signed.version = 0  # `close` will bump to initial valid verison 1
            self.close(signed.type, Metadata(signed))

    def add_target_files(self, target_files: List[TargetFile]) -> None:
        """Add target files to top-level targets metadata."""
        with self.edit_targets() as targets:
            for target_file in target_files:
                targets.targets[target_file.path] = target_file

        self.do_snapshot()
        self.do_timestamp()

    def add_keys(self, keys: List[Key], role: str) -> None:
        """Add public keys for role to root."""
        with self.edit_root() as root:
            for key in keys:
                root.add_key(key, role)

        self.do_snapshot()
        self.do_timestamp()
