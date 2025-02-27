import datetime
import pytest
from taf.messages import git_commit_message
from freezegun import freeze_time
from typing import Dict
from taf.auth_repo import AuthenticationRepository
from taf.api.repository import create_repository
from taf.api.metadata import check_expiration_dates, update_metadata_expiration_date

from tuf.api.metadata import Root, Snapshot, Timestamp, Targets
from taf.yubikey.yubikey_manager import PinManager


AUTH_REPO_NAME = "auth"


@pytest.fixture(scope="module")
@freeze_time("2021-12-31")
def auth_repo_expired(
    api_repo_path,
    keystore_delegations,
    with_delegations_no_yubikeys_path,
    pin_manager,
):
    repo_path = str(api_repo_path)
    create_repository(
        repo_path,
        pin_manager,
        roles_key_infos=str(with_delegations_no_yubikeys_path),
        keystore=keystore_delegations,
        commit=True,
        test=True,
    )
    auth_repo = AuthenticationRepository(path=repo_path)
    return auth_repo


@freeze_time("2023-01-01")
def test_check_expiration_date_when_all_expired(
    auth_repo_expired: AuthenticationRepository,
):
    expired, will_expire = check_expiration_dates(
        auth_repo_expired.path, print_output=False
    )
    start = datetime.datetime(2021, 12, 31, tzinfo=datetime.timezone.utc)
    # expect expire after 1 day
    _check_expired_role(Timestamp.type, start, 1, expired)
    # expect expired after 7 days
    _check_expired_role(Snapshot.type, start, 7, expired)
    # expect expire after 3 months
    for target_role in (Targets.type, "delegated_role", "inner_role"):
        _check_expired_role(target_role, start, 90, expired)
    # expect expire after one year
    _check_expired_role(Root.type, start, 365, expired)
    assert not len(will_expire)


@freeze_time("2023-01-01")
def test_update_root_metadata(
    auth_repo_expired: AuthenticationRepository,
    keystore_delegations: str,
    pin_manager: PinManager,
):
    # update root metadata, expect snapshot and timestamp to be updated too
    # targets should not be updated
    auth_repo_path = auth_repo_expired.path
    auth_repo = AuthenticationRepository(path=auth_repo_path)
    initial_commits_num = len(auth_repo.list_pygit_commits())
    roles = [Root.type]
    INTERVAL = 180
    timestamp_version = auth_repo_expired.timestamp().version
    snapshot_version = auth_repo_expired.snapshot().version
    update_metadata_expiration_date(
        path=auth_repo_path,
        pin_manager=pin_manager,
        roles=roles,
        interval=INTERVAL,
        keystore=keystore_delegations,
        push=False,
    )
    commits = auth_repo.list_pygit_commits()
    assert len(commits) == initial_commits_num + 1
    assert commits[0].message.strip() == git_commit_message(
        "update-expiration-dates", roles=",".join(roles)
    )
    expected_expiration = _get_date(INTERVAL)
    actual_expiration = auth_repo.get_expiration_date(Root.type)
    assert expected_expiration == actual_expiration
    now = datetime.datetime.now(tz=datetime.timezone.utc)
    for role in (Targets.type, "delegated_role", "inner_role"):
        actual_expiration = auth_repo.get_expiration_date(role)
        assert actual_expiration < now
    assert auth_repo_expired.timestamp().version == timestamp_version + 1
    assert auth_repo_expired.snapshot().version == snapshot_version + 1


@freeze_time("2023-01-01")
def test_check_expiration_date_when_expired_and_will_expire(
    auth_repo_expired: AuthenticationRepository,
):
    auth_repo_path = auth_repo_expired.path
    expired, will_expire = check_expiration_dates(
        auth_repo_path, interval=90, print_output=False
    )

    start = datetime.datetime(2021, 12, 31, tzinfo=datetime.timezone.utc)
    # target roles have not been updated yet
    for target_role in (Targets.type, "delegated_role", "inner_role"):
        _check_expired_role(target_role, start, 90, expired)

    # other roles are not due to expire in the specified interval
    assert not len(will_expire)

    # now set a larger interval, all roles are due to expire before the interval's end
    _, will_expire = check_expiration_dates(
        auth_repo_path, interval=366, print_output=False
    )
    assert Root.type in will_expire


@freeze_time("2023-01-01")
def test_update_snapshot_metadata(
    auth_repo_expired: AuthenticationRepository,
    keystore_delegations: str,
    pin_manager: PinManager,
):
    # update root metadata, expect snapshot and timestamp to be updated too
    # targets should not be updated
    auth_repo_path = auth_repo_expired.path
    auth_repo = AuthenticationRepository(path=auth_repo_path)
    initial_commits_num = len(auth_repo.list_pygit_commits())
    roles = [Snapshot.type]
    INTERVAL = 7
    timestamp_version = auth_repo_expired.timestamp().version
    snapshot_version = auth_repo_expired.snapshot().version
    update_metadata_expiration_date(
        path=auth_repo_path,
        pin_manager=pin_manager,
        roles=roles,
        interval=INTERVAL,
        keystore=keystore_delegations,
        push=False,
    )
    commits = auth_repo.list_pygit_commits()
    assert len(commits) == initial_commits_num + 1
    assert commits[0].message.strip() == git_commit_message(
        "update-expiration-dates", roles=",".join(roles)
    )
    assert auth_repo_expired.timestamp().version == timestamp_version + 1
    assert auth_repo_expired.snapshot().version == snapshot_version + 1


@freeze_time("2023-01-01")
def test_update_timestamp_metadata(
    auth_repo_expired: AuthenticationRepository,
    keystore_delegations: str,
    pin_manager: PinManager,
):
    # update root metadata, expect snapshot and timestamp to be updated too
    # targets should not be updated
    auth_repo_path = auth_repo_expired.path
    auth_repo = AuthenticationRepository(path=auth_repo_path)
    initial_commits_num = len(auth_repo.list_pygit_commits())
    roles = [Timestamp.type]
    INTERVAL = 1
    timestamp_version = auth_repo_expired.timestamp().version
    snapshot_version = auth_repo_expired.snapshot().version
    update_metadata_expiration_date(
        path=auth_repo_path,
        pin_manager=pin_manager,
        roles=roles,
        interval=INTERVAL,
        keystore=keystore_delegations,
        push=False,
    )
    commits = auth_repo.list_pygit_commits()
    assert len(commits) == initial_commits_num + 1
    assert commits[0].message.strip() == git_commit_message(
        "update-expiration-dates", roles=",".join(roles)
    )
    assert auth_repo_expired.timestamp().version == timestamp_version + 1
    assert auth_repo_expired.snapshot().version == snapshot_version


@freeze_time("2023-01-01")
def test_update_multiple_roles_metadata(
    auth_repo_expired: AuthenticationRepository,
    keystore_delegations: str,
    pin_manager: PinManager,
):
    # update root metadata, expect snapshot and timestamp to be updated too
    # targets should not be updated
    auth_repo_path = auth_repo_expired.path
    auth_repo = AuthenticationRepository(path=auth_repo_path)
    initial_commits_num = len(auth_repo.list_pygit_commits())
    roles = [Targets.type, "delegated_role", "inner_role"]
    INTERVAL = 365
    timestamp_version = auth_repo_expired.timestamp().version
    snapshot_version = auth_repo_expired.snapshot().version
    update_metadata_expiration_date(
        path=auth_repo_path,
        pin_manager=pin_manager,
        roles=roles,
        interval=INTERVAL,
        keystore=keystore_delegations,
        push=False,
    )
    commits = auth_repo.list_pygit_commits()
    assert len(commits) == initial_commits_num + 1
    assert commits[0].message.strip() == git_commit_message(
        "update-expiration-dates", roles=",".join(roles)
    )
    for role in roles:
        expected_expiration = _get_date(INTERVAL)
        actual_expiration = auth_repo.get_expiration_date(role)
        assert expected_expiration == actual_expiration
    assert auth_repo_expired.timestamp().version == timestamp_version + 1
    assert auth_repo_expired.snapshot().version == snapshot_version + 1


@freeze_time("2023-01-01")
def test_check_expiration_date_when_no_expired(
    auth_repo_expired: AuthenticationRepository,
):
    auth_repo_path = auth_repo_expired.path
    expired, will_expire = check_expiration_dates(
        auth_repo_path, interval=90, print_output=False
    )
    assert not len(expired)
    assert len(will_expire) == 2


def _check_expired_role(
    role_name: str, start_time: datetime.datetime, interval: int, expired_dict: Dict
):
    assert role_name in expired_dict
    expected_expiration_date = start_time + datetime.timedelta(days=interval)
    actual_expiration_time = expired_dict[role_name]
    # strip hours and minutes, they are set in case of targets and root
    actual_expiration_date = _strip_hours(actual_expiration_time)
    assert expected_expiration_date == actual_expiration_date


def _get_date(interval):
    now = datetime.datetime.now(tz=datetime.timezone.utc)
    date = now + datetime.timedelta(interval)
    return _strip_hours(date)


def _strip_hours(date):
    return datetime.datetime(
        date.year,
        date.month,
        date.day,
        tzinfo=date.tzinfo,
    )
