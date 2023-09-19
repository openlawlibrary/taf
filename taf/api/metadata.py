from datetime import datetime
from logging import DEBUG, ERROR, INFO
from pathlib import Path
from typing import Dict, List, Optional
from logdecorator import log_on_end, log_on_error, log_on_start
from taf.api.utils import check_if_clean, commit_and_push
from taf.exceptions import TAFError
from taf.git import GitRepository
from taf.keys import load_signing_keys
from taf.constants import DEFAULT_RSA_SIGNATURE_SCHEME
from taf.repository_tool import Repository, is_delegated_role
from taf.log import taf_logger


@log_on_error(
    ERROR,
    "An error occurred while checking expiration dates: {e!r}",
    logger=taf_logger,
    on_exceptions=TAFError,
    reraise=False,
)
def check_expiration_dates(
    path: str,
    interval: Optional[int] = None,
    start_date: Optional[datetime] = None,
    excluded_roles: Optional[List[str]] = None,
) -> None:
    """
    Check if any metadata files (roles) are expired or will expire in the next <interval> days.
    Prints a list of expired roles.

    Arguments:
        path: Authentication repository's location.
        interval: Number of days ahead to check for expiration.
        start_date: Date from which to start checking for expiration.
        excluded_roles: List of roles to exclude from the check.

    Side Effects:
        Prints lists of roles that expired or are about to expire.

    Returns:
        None
    """
    path = Path(path)
    taf_repo = Repository(path)

    expired_dict, will_expire_dict = taf_repo.check_roles_expiration_dates(
        interval, start_date, excluded_roles
    )

    if expired_dict or will_expire_dict:
        now = datetime.now()
        print(
            f"Given a {interval} day interval from today ({start_date.strftime('%Y-%m-%d')}):"
        )
        for role, expiry_date in expired_dict.items():
            delta = now - expiry_date
            print(
                f"{role} expired {delta.days} days ago (on {expiry_date.strftime('%Y-%m-%d')})"
            )
        for role, expiry_date in will_expire_dict.items():
            delta = expiry_date - now
            print(
                f"{role} will expire in {delta.days} days (on {expiry_date.strftime('%Y-%m-%d')})"
            )
    else:
        print(f"No roles will expire within the given {interval} day interval")


@check_if_clean
def update_metadata_expiration_date(
    path: str,
    roles: List[str],
    interval: int,
    keystore: Optional[str] = None,
    scheme: Optional[str] = None,
    start_date: Optional[datetime] = None,
    commit: Optional[bool] = True,
    prompt_for_keys: Optional[bool] = False,
) -> None:
    """
    Update expiration dates of the specified roles and all other roles that need
    to be signed in order to guarantee validity of the repository e.g. snapshot
    and timestamp need to be signed after a targets role is updated.

    Arguments:
        path: Authentication repository's location.
        roles: A list of roles whose expiration dates should be updated.
        interval: Number of days added to the start date in order to calculate the
            expiration date.
        keystore (optional): Keystore directory's path
        scheme (optional): Signature scheme.
        start_date (optional): Date to which expiration interval is added.
            Set to today if not specified.
        prompt_for_keys (optional): Whether to ask the user to enter their key if it is not located inside the keystore directory.
        commit (optional): Indicates if the changes should be committed and pushed automatically.

    Side Effects:
        Updates metadata files, saves changes to disk and commits changes
        unless no_commit is set to True.

    Returns:
        None
    """
    if start_date is None:
        start_date = datetime.now()

    taf_repo = Repository(path)
    loaded_yubikeys = {}
    roles_to_update = []

    if "root" in roles:
        roles_to_update.append("root")
    if "targets" in roles:
        roles_to_update.append("targets")
    for role in roles:
        if is_delegated_role(role):
            roles_to_update.append(role)

    if len(roles_to_update) or "snapshot" in roles:
        roles_to_update.append("snapshot")
    roles_to_update.append("timestamp")

    for role in roles_to_update:
        _update_expiration_date_of_role(
            taf_repo,
            role,
            loaded_yubikeys,
            keystore,
            start_date,
            interval,
            scheme,
            prompt_for_keys,
        )

    if not commit:
        print("\nPlease commit manually. \n")
    else:
        auth_repo = GitRepository(path=path)
        commit_and_push(auth_repo)


@log_on_end(INFO, "Updated expiration date of {role:s}", logger=taf_logger)
@log_on_error(
    ERROR,
    "Error: could not update expiration date: {e}",
    logger=taf_logger,
    on_exceptions=TAFError,
    reraise=True,
)
def _update_expiration_date_of_role(
    auth_repo: Repository,
    role: str,
    loaded_yubikeys: Dict,
    keystore: str,
    start_date: datetime,
    interval: int,
    scheme: str,
    prompt_for_keys: bool,
) -> None:
    keys, yubikeys = load_signing_keys(
        auth_repo,
        role,
        loaded_yubikeys=loaded_yubikeys,
        keystore=keystore,
        scheme=scheme,
        prompt_for_keys=prompt_for_keys,
    )
    # sign with keystore
    if len(keys):
        auth_repo.update_role_keystores(
            role, keys, start_date=start_date, interval=interval
        )
    if len(yubikeys):  # sign with yubikey
        auth_repo.update_role_yubikeys(
            role, yubikeys, start_date=start_date, interval=interval
        )


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

    Side Effects:
        Updates metadata files, saves changes to disk if write_all is True

    Returns:
        None
    """
    loaded_yubikeys = {}

    for role in ("snapshot", "timestamp"):
        keystore_keys, yubikeys = load_signing_keys(
            taf_repo,
            role,
            keystore,
            loaded_yubikeys,
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
) -> None:
    """Given dictionaries containing targets that should be added and targets that should
    be removed, update and sign target metadata files and, if write is True, also
    sign snapshot and timestamp.

    Sign snapshot and timestamp metadata files

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
    loaded_yubikeys = {}
    for role, target_paths in roles_targets.items():
        keystore_keys, yubikeys = load_signing_keys(
            taf_repo,
            role,
            keystore,
            loaded_yubikeys,
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
