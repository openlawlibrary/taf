from datetime import datetime, timezone
from logging import INFO, ERROR
from typing import Dict, List, Optional, Tuple
from logdecorator import log_on_end, log_on_error
from taf.api.utils._conf import find_keystore
from taf.api.utils._git import check_if_clean
from taf.api.api_workflow import manage_repo_and_signers
from taf.exceptions import TAFError
from taf.keys import load_signers
from taf.constants import DEFAULT_RSA_SIGNATURE_SCHEME
from taf.messages import git_commit_message
from taf.tuf.repository import MetadataRepository as TUFRepository, is_delegated_role
from taf.log import taf_logger
from taf.auth_repo import AuthenticationRepository


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



@check_if_clean
def update_metadata_expiration_date(
    path: str,
    roles: List[str],
    interval: Optional[int] = None,
    keystore: Optional[str] = None,
    scheme: Optional[str] = DEFAULT_RSA_SIGNATURE_SCHEME,
    start_date: Optional[datetime] = None,
    commit: Optional[bool] = True,
    prompt_for_keys: Optional[bool] = False,
    push: Optional[bool] = True,
    update_snapshot_and_timestamp: Optional[bool] = True,
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
        prompt_for_keys (optional): Whether to ask the user to enter their key if it is not located inside the keystore directory.
        push (optional): Flag specifying whether to push to remote

    Side Effects:
        Updates metadata files, saves changes to disk and commits changes
        unless no_commit is set to True.

    Returns:
        None
    """

    auth_repo = AuthenticationRepository(path=path)
    if start_date is None:
        start_date = datetime.now()

    roles_to_update = set(roles)
    if update_snapshot_and_timestamp:
        update_snapshot_and_timestamp = (
            "timestamp" not in roles_to_update or len(roles_to_update) > 1
        )
    if update_snapshot_and_timestamp:
        roles_to_update.add("snapshot")
        roles_to_update.add("timestamp")

    commit_msg = git_commit_message(
        "update-expiration-dates", roles=",".join(roles)
    )

    with manage_repo_and_signers(
        auth_repo,
        roles_to_update,
        keystore,
        scheme,
        prompt_for_keys,
        load_snapshot_and_timestamp=update_snapshot_and_timestamp,
        commit=commit,
        commit_msg=commit_msg,
        push=push
    ):
        for role in roles_to_update:
            auth_repo.set_metadata_expiration_date(
                role, start_date=start_date, interval=interval
            )
