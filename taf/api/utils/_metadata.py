from logging import DEBUG, ERROR, INFO
from typing import Dict, Optional
from logdecorator import log_on_end, log_on_error, log_on_start
from taf.exceptions import TAFError
from taf.keys import load_signing_keys
from taf.constants import DEFAULT_RSA_SIGNATURE_SCHEME
from taf.repository_tool import Repository
from taf.log import taf_logger


@log_on_end(INFO, "Updated snapshot and timestamp", logger=taf_logger)
@log_on_error(
    ERROR,
    "Could not update snapshot and timestamp: {e}",
    logger=taf_logger,
    on_exceptions=TAFError,
    reraise=True,
)
def update_snapshot_and_timestamp(
    taf_repo: Repository,
    keystore: str,
    scheme: Optional[str] = DEFAULT_RSA_SIGNATURE_SCHEME,
    write_all: Optional[bool] = True,
    prompt_for_keys: Optional[bool] = False,
) -> None:
    """
    Sign snapshot and timestamp metadata files.

    Arguments:
        taf_repo: Authentication repository.
        keystore: Keystore directory's path.
        scheme (optional): Signature scheme.
        write_all (optional): If True, writes authentication repository's
            changes to disk.
        prompt_for_keys (optional): Whether to ask the user to enter their key if it is not located inside the keystore directory.
        push (optional): Flag specifying whether to push to remote

    Side Effects:
        Updates metadata files, saves changes to disk if write_all is True

    Returns:
        None
    """
    loaded_yubikeys: Dict = {}

    for role in ("snapshot", "timestamp"):
        keystore_keys, yubikeys = load_signing_keys(
            taf_repo,
            role,
            loaded_yubikeys,
            keystore,
            scheme=scheme,
            prompt_for_keys=prompt_for_keys,
        )
        if len(yubikeys):
            update_method = taf_repo.roles_yubikeys_update_method(role)
            update_method(yubikeys, write=False)
        if len(keystore_keys):
            update_method = taf_repo.roles_keystore_update_method(role)
            update_method(keystore_keys, write=False)

    if write_all:
        taf_repo.writeall()


@log_on_start(DEBUG, "Updating target metadata", logger=taf_logger)
@log_on_end(DEBUG, "Updated target metadata", logger=taf_logger)
@log_on_error(
    ERROR,
    "Could not update target metadata: {e}",
    logger=taf_logger,
    on_exceptions=TAFError,
    reraise=True,
)
def update_target_metadata(
    taf_repo: Repository,
    added_targets_data: Dict,
    removed_targets_data: Dict,
    keystore: str,
    write: Optional[bool] = False,
    scheme: Optional[str] = DEFAULT_RSA_SIGNATURE_SCHEME,
    prompt_for_keys: Optional[bool] = False,
) -> bool:
    """Given dictionaries containing targets that should be added and targets that should
    be removed, update and sign target metadata files and, if write is True, also
    sign snapshot and timestamp.

    Arguments:
        taf_repo: Authentication repository.
        added_targets_data(dict): Dictionary containing targets data that should be added.
        removed_targets_data(dict): Dictionary containing targets data that should be removed.
        keystore: Keystore directory's path.
        write (optional): If True, updates snapshot and timestamp and write changes to disk.
        scheme (optional): Signature scheme.
        prompt_for_keys (optional): Whether to ask the user to enter their key if it is not located inside the keystore directory.

    Side Effects:
        Updates metadata files, saves changes to disk if write_all is True

    Returns:
        True if there were targets that were updated, False otherwise
    """
    added_targets_data = {} if added_targets_data is None else added_targets_data
    removed_targets_data = {} if removed_targets_data is None else removed_targets_data

    roles_targets = taf_repo.roles_targets_for_filenames(
        list(added_targets_data.keys()) + list(removed_targets_data.keys())
    )

    if not roles_targets:
        taf_logger.info("No target files to sign")
        return False

    # update targets
    loaded_yubikeys: Dict = {}
    for role, target_paths in roles_targets.items():
        keystore_keys, yubikeys = load_signing_keys(
            taf_repo,
            role,
            loaded_yubikeys,
            keystore,
            scheme=scheme,
            prompt_for_keys=prompt_for_keys,
        )
        targets_data = dict(
            added_targets_data={
                path: val
                for path, val in added_targets_data.items()
                if path in target_paths
            },
            removed_targets_data={
                path: val
                for path, val in removed_targets_data.items()
                if path in target_paths
            },
        )

        if len(yubikeys):
            taf_repo.update_targets_yubikeys(yubikeys, write=False, **targets_data)
        if len(keystore_keys):
            taf_repo.update_targets_keystores(
                keystore_keys, write=False, **targets_data
            )

    if write:
        update_snapshot_and_timestamp(
            taf_repo, keystore, scheme=scheme, prompt_for_keys=prompt_for_keys
        )
    return True
