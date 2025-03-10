from datetime import datetime, timezone
from logging import ERROR
from typing import Dict, List, Optional, Tuple
from logdecorator import log_on_error
from taf.api.utils._conf import read_keys_name_mapping
from taf.yubikey.yubikey_manager import PinManager
from tuf.api.metadata import Snapshot, Timestamp

from taf.api.utils._git import check_if_clean_and_synced
from taf.api.api_workflow import manage_repo_and_signers
from taf.exceptions import TAFError
from taf.constants import DEFAULT_RSA_SIGNATURE_SCHEME
from taf.messages import git_commit_message
from taf.tuf.repository import MetadataRepository as TUFRepository
from taf.log import Path, taf_logger
from taf.auth_repo import AuthenticationRepository


@log_on_error(
    ERROR,
    "An error occurred while adding key names: {e}",
    logger=taf_logger,
    on_exceptions=TAFError,
    reraise=False,
)
@check_if_clean_and_synced
def add_key_names(
    path: str,
    keys_description: Path,
    pin_manager: PinManager,
    scheme: Optional[str] = DEFAULT_RSA_SIGNATURE_SCHEME,
    keystore: Optional[str] = None,
    commit: Optional[bool] = True,
    commit_msg: Optional[str] = None,
    prompt_for_keys: Optional[bool] = False,
    push: Optional[bool] = True,
    update_snapshot_and_timestamp: Optional[bool] = True,
):
    if not keys_description.is_file():
        raise TAFError(f"{keys_description} does not exist")

    commit_msg = commit_msg or git_commit_message("add-key-names")

    keys_name_mappings = read_keys_name_mapping(keys_description)
    if not keys_name_mappings:
        raise TAFError(f"{keys_description} is not a valid keys description json file")

    auth_repo = AuthenticationRepository(path=path, pin_manager=pin_manager)
    existing_mapping = auth_repo.keys_name_mappings
    for key_id, key_name in dict(keys_name_mappings).items():
        if key_id in existing_mapping and key_name == keys_name_mappings[key_id]:
            keys_name_mappings.pop(key_id)

    if not len(keys_name_mappings):
        taf_logger.log("NOTICE", "All names already added to the repository")
        return

    auth_repo.add_key_names(keys_name_mappings)
    parent_roles = set()
    for key_id in keys_name_mappings:
        roles_of_key = auth_repo.find_keysid_roles([key_id], check_threshold=False)
        # map the roles to the roles that contain their keys
        for role_of_key in roles_of_key:
            role_containing_key = auth_repo.find_role_containing_key_of_role(
                role_of_key
            )
            if role_containing_key is not None:
                parent_roles.add(role_containing_key)

    with manage_repo_and_signers(
        auth_repo,
        list(parent_roles),
        keystore,
        scheme,
        prompt_for_keys,
        load_snapshot_and_timestamp=update_snapshot_and_timestamp,
        commit=commit,
        commit_msg=commit_msg,
        push=push,
    ):
        auth_repo.set_key_names(keys_name_mappings)
        if update_snapshot_and_timestamp:
            auth_repo.update_snapshot_and_timestamp()


@log_on_error(
    ERROR,
    "An error occurred while checking expiration dates: {e!r}",
    logger=taf_logger,
    on_exceptions=TAFError,
    reraise=False,
)
def check_expiration_dates(
    path: str,
    interval: Optional[int] = 30,
    start_date: Optional[datetime] = None,
    excluded_roles: Optional[List[str]] = None,
    print_output: bool = True,
) -> Tuple[Dict, Dict]:
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
    taf_repo = TUFRepository(path)

    if start_date is None:
        start_date = datetime.now(timezone.utc)
    elif start_date.tzinfo is None:
        start_date = start_date.replace(tzinfo=timezone.utc)

    expired_dict, will_expire_dict = taf_repo.check_roles_expiration_dates(
        interval, start_date, excluded_roles
    )

    if print_output:
        print_expiration_dates(
            expired_dict, will_expire_dict, start_date=start_date, interval=interval
        )

    return expired_dict, will_expire_dict


def print_expiration_dates(
    expired: Dict, will_expire: Dict, start_date: datetime, interval: Optional[int] = 30
) -> None:
    if expired or will_expire:
        now = datetime.now(timezone.utc)
        print(
            f"Given a {interval} day interval from ({start_date.strftime('%Y-%m-%d')}):"
        )
        for role, expiry_date in expired.items():
            delta = now - expiry_date
            print(
                f"{role} expired {delta.days} days ago (on {expiry_date.strftime('%Y-%m-%d')})"
            )
        for role, expiry_date in will_expire.items():
            delta = expiry_date - now
            print(
                f"{role} will expire in {delta.days} days (on {expiry_date.strftime('%Y-%m-%d')})"
            )
    else:
        print(f"No roles will expire within the given {interval} day interval")


@check_if_clean_and_synced
def update_metadata_expiration_date(
    path: str,
    pin_manager: PinManager,
    roles: List[str],
    interval: Optional[int] = None,
    keystore: Optional[str] = None,
    scheme: Optional[str] = DEFAULT_RSA_SIGNATURE_SCHEME,
    start_date: Optional[datetime] = None,
    commit: Optional[bool] = True,
    commit_msg: Optional[str] = None,
    prompt_for_keys: Optional[bool] = False,
    push: Optional[bool] = True,
    update_snapshot_and_timestamp: Optional[bool] = True,
    keys_description: Optional[str] = None,
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
        commit (optional): Indicates if the changes should be committed and pushed automatically.
        commit_msg (optional): Custom commit messages.
        prompt_for_keys (optional): Whether to ask the user to enter their key if it is not located inside the keystore directory.
        push (optional): Flag specifying whether to push to remote

    Side Effects:
        Updates metadata files, saves changes to disk and commits changes
        unless no_commit is set to True.

    Returns:
        None
    """

    auth_repo = AuthenticationRepository(path=path, pin_manager=pin_manager)
    keys_name_mappings = read_keys_name_mapping(keys_description)
    auth_repo.add_key_names(keys_name_mappings)
    if start_date is None:
        start_date = datetime.now()

    commit_msg = commit_msg or git_commit_message(
        "update-expiration-dates", roles=",".join(roles)
    )

    # update the order, snapshot has to be updated before timestamp
    # and all other roles have to be updated before snapshot
    # all other roles can be updated in any order

    update_snapshot_expiration_date = Snapshot.type in roles
    update_timestamp_expiration_date = Timestamp.type in roles

    with manage_repo_and_signers(
        auth_repo,
        roles,
        keystore,
        scheme,
        prompt_for_keys,
        load_snapshot_and_timestamp=update_snapshot_and_timestamp,
        commit=commit,
        commit_msg=commit_msg,
        push=push,
    ):
        if update_snapshot_expiration_date:
            auth_repo.add_to_open_metadata([Snapshot.type])
        if update_timestamp_expiration_date:
            auth_repo.add_to_open_metadata([Timestamp.type])

        for role in roles:
            auth_repo.set_metadata_expiration_date(
                role, start_date=start_date, interval=interval
            )

        auth_repo.remove_from_open_metadata([Snapshot.type])
        # it is important to update snapshot first

        if (update_snapshot_expiration_date or update_snapshot_and_timestamp) and not (
            len(roles) == 1 and update_timestamp_expiration_date
        ):
            auth_repo.do_snapshot(force=True)

        auth_repo.remove_from_open_metadata([Timestamp.type])
        if update_timestamp_expiration_date or update_snapshot_and_timestamp:
            auth_repo.do_timestamp(force=True)


@check_if_clean_and_synced
def update_snapshot_and_timestamp(
    path: str,
    pin_manager: PinManager,
    keystore: Optional[str] = None,
    roles_to_sync: Optional[List[str]] = None,
    scheme: Optional[str] = DEFAULT_RSA_SIGNATURE_SCHEME,
    commit: Optional[bool] = True,
    commit_msg: Optional[str] = None,
    prompt_for_keys: Optional[bool] = False,
    push: Optional[bool] = True,
    update_expiration_dates: Optional[bool] = True,
    keys_description: Optional[str] = None,
) -> None:
    """
    Update expiration snapshot and timestamp

    Arguments:
        path: Authentication repository's location.
        keystore (optional): Keystore directory's path
        scheme (optional): Signature scheme.
        commit (optional): Indicates if the changes should be committed and pushed automatically.
        commit_msg (optional): Custom commit messages.
        prompt_for_keys (optional): Whether to ask the user to enter their key if it is not located inside the keystore directory.
        push (optional): Flag specifying whether to push to remote
        update_expiration_dates (optional): Flag specifying whether to update expiration dates

    Side Effects:
        Updates metadata files, saves changes to disk and commits changes
        unless no_commit is set to True.

    Returns:
        None
    """

    auth_repo = AuthenticationRepository(path=path, pin_manager=pin_manager)
    keys_name_mappings = read_keys_name_mapping(keys_description)
    auth_repo.add_key_names(keys_name_mappings)

    with manage_repo_and_signers(
        auth_repo,
        [],
        keystore,
        scheme,
        prompt_for_keys,
        load_snapshot_and_timestamp=True,
        commit=commit,
        commit_msg=commit_msg,
        push=push,
    ):
        if update_expiration_dates:
            auth_repo.add_to_open_metadata([Snapshot.type, Timestamp.type])
            for role in [Snapshot.type, Timestamp.type]:
                auth_repo.set_metadata_expiration_date(role)
            auth_repo.clear_open_metadata()
        if roles_to_sync:
            auth_repo.sync_snapshot_with_roles(roles_to_sync)
            auth_repo.do_timestamp(force=True)
        else:
            auth_repo.update_snapshot_and_timestamp()
