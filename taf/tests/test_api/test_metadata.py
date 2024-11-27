import datetime
import pytest
from taf.messages import git_commit_message
from freezegun import freeze_time
from typing import Dict
from taf.auth_repo import AuthenticationRepository
from taf.api.repository import create_repository
from taf.api.metadata import check_expiration_dates, update_metadata_expiration_date


AUTH_REPO_NAME = "auth"


@pytest.fixture(scope="module")
@freeze_time("2021-12-31")
def auth_repo_expired(
    api_repo_path, keystore_delegations, with_delegations_no_yubikeys_path
):
    repo_path = str(api_repo_path)
    create_repository(
        repo_path,
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
    _check_expired_role("timestamp", start, 1, expired)
    # expect expired after 7 days
    _check_expired_role("snapshot", start, 7, expired)
    # expect expire after 3 months
    for target_role in ("targets", "delegated_role", "inner_role"):
        _check_expired_role(target_role, start, 90, expired)
    # expect expire after one year
    _check_expired_role("root", start, 365, expired)
    assert not len(will_expire)


@freeze_time("2023-01-01")
def test_update_root_metadata(
    auth_repo_expired: AuthenticationRepository, keystore_delegations: str
):
    # update root metadata, expect snapshot and timestamp to be updated too
    # targets should not be updated
    auth_repo_path = auth_repo_expired.path
    auth_repo = AuthenticationRepository(path=auth_repo_path)
    initial_commits_num = len(auth_repo.list_commits())
    roles = ["root"]
    INTERVAL = 180
    update_metadata_expiration_date(
        path=auth_repo_path,
        roles=roles,
        interval=INTERVAL,
        keystore=keystore_delegations,
        push=False,
    )
    commits = auth_repo.list_commits()
    assert len(commits) == initial_commits_num + 1
    assert commits[0].message.strip() == git_commit_message(
        "update-expiration-dates", roles=",".join(roles)
    )
    for role in ("root", "snapshot", "timestamp"):
        expected_expiration = _get_date(INTERVAL)
        actual_expiration = auth_repo.get_expiration_date(role)
        assert expected_expiration == actual_expiration
    now = datetime.datetime.now(tz=datetime.timezone.utc)
    for role in ("targets", "delegated_role", "inner_role"):
        actual_expiration = auth_repo.get_expiration_date(role)
        assert actual_expiration < now


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
    for target_role in ("targets", "delegated_role", "inner_role"):
        _check_expired_role(target_role, start, 90, expired)

    # other roles are not due to expire in the specified interval
    assert not len(will_expire)

    # now set a larger interval, all roles are due to expire before the interval's end
    _, will_expire = check_expiration_dates(
        auth_repo_path, interval=365, print_output=False
    )
    assert len(will_expire) == 3
    for role in ("root", "snapshot", "timestamp"):
        assert role in will_expire


@freeze_time("2023-01-01")
def test_update_multiple_roles_metadata(
    auth_repo_expired: AuthenticationRepository, keystore_delegations: str
):
    # update root metadata, expect snapshot and timestamp to be updated too
    # targets should not be updated
    auth_repo_path = auth_repo_expired.path
    auth_repo = AuthenticationRepository(path=auth_repo_path)
    initial_commits_num = len(auth_repo.list_commits())
    roles = ["targets", "delegated_role", "inner_role"]
    INTERVAL = 365
    update_metadata_expiration_date(
        path=auth_repo_path,
        roles=roles,
        interval=INTERVAL,
        keystore=keystore_delegations,
        push=False,
    )
    commits = auth_repo.list_commits()
    assert len(commits) == initial_commits_num + 1
    assert commits[0].message.strip() == git_commit_message(
        "update-expiration-dates", roles=",".join(roles)
    )
    for role in roles + ["snapshot", "timestamp"]:
        expected_expiration = _get_date(INTERVAL)
        actual_expiration = auth_repo.get_expiration_date(role)
        assert expected_expiration == actual_expiration


@freeze_time("2023-01-01")
def test_check_expiration_date_when_no_expired(
    auth_repo_expired: AuthenticationRepository,
):
    auth_repo_path = auth_repo_expired.path
    expired, will_expire = check_expiration_dates(
        auth_repo_path, interval=90, print_output=False
    )
    assert not len(expired)
    assert not len(will_expire)


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
