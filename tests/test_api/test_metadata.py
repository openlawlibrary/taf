import datetime
import shutil
import uuid
from freezegun import freeze_time
from pathlib import Path
from typing import Dict
from taf.messages import git_commit_message
from taf.auth_repo import AuthenticationRepository
from pytest import fixture
from taf.api.repository import create_repository
from taf.tests.conftest import CLIENT_DIR_PATH
from taf.utils import on_rm_error
from taf.api.metadata import check_expiration_dates, update_metadata_expiration_date


AUTH_REPO_NAME = "auth"


@fixture(scope="module")
def auth_repo_path():
    random_name = str(uuid.uuid4())
    root_dir = CLIENT_DIR_PATH / random_name
    auth_path = root_dir / AUTH_REPO_NAME
    auth_path.mkdir(exist_ok=True, parents=True)
    yield auth_path
    shutil.rmtree(root_dir, onerror=on_rm_error)


@freeze_time("2021-12-31")
def test_setup_auth_repo_expired(
    auth_repo_path: Path,
    with_delegations_no_yubikeys_path: str,
    api_keystore: str,
):

    create_repository(
        str(auth_repo_path),
        roles_key_infos=with_delegations_no_yubikeys_path,
        keystore=api_keystore,
        commit=True,
    )


@freeze_time("2023-01-01")
def test_check_expiration_date_when_all_expired(auth_repo_path: Path):
    expired, will_expire = check_expiration_dates(auth_repo_path, print_output=False)
    start = datetime.datetime(2021, 12, 31)
    # expect expire after 1 day
    _check_expired_role("timestamp", start, 1, expired)
    # expect expired after 7 days
    _check_expired_role("snapshot", start, 7, expired)
    # expect expire after 3 months
    for target_role in ("targets", "delegated_role", "inner_role"):
        _check_expired_role(target_role, start, 91, expired)
    # expect expire after one year
    _check_expired_role("root", start, 365, expired)
    assert not len(will_expire)


@freeze_time("2023-01-01")
def test_update_root_metadata(auth_repo_path: Path, api_keystore: str):
    # update root metadata, expect snapshot and timestamp to be updated too
    # targets should not be updated
    auth_repo = AuthenticationRepository(path=auth_repo_path)
    initial_commits_num = len(auth_repo.list_commits())
    roles = ["root"]
    INTERVAL = 180
    update_metadata_expiration_date(
        path=auth_repo_path,
        roles=roles,
        interval=INTERVAL,
        keystore=api_keystore,
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
    now = datetime.datetime.now()
    for role in ("targets", "delegated_role", "inner_role"):
        actual_expiration = auth_repo.get_expiration_date(role)
        assert actual_expiration < now


@freeze_time("2023-01-01")
def test_check_expiration_date_when_expired_and_will_expire(auth_repo_path: Path):
    expired, will_expire = check_expiration_dates(
        auth_repo_path, interval=90, print_output=False
    )

    start = datetime.datetime(2021, 12, 31)
    # target roles have not been updated yet
    for target_role in ("targets", "delegated_role", "inner_role"):
        _check_expired_role(target_role, start, 91, expired)

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
def test_update_multiple_roles_metadata(auth_repo_path: Path, api_keystore: str):
    # update root metadata, expect snapshot and timestamp to be updated too
    # targets should not be updated
    auth_repo = AuthenticationRepository(path=auth_repo_path)
    initial_commits_num = len(auth_repo.list_commits())
    roles = ["targets", "delegated_role", "inner_role"]
    INTERVAL = 365
    update_metadata_expiration_date(
        path=auth_repo_path,
        roles=roles,
        interval=INTERVAL,
        keystore=api_keystore,
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
def test_check_expiration_date_when_no_expired(auth_repo_path: Path):
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
    now = datetime.datetime.now()
    date = now + datetime.timedelta(interval)
    return _strip_hours(date)


def _strip_hours(date):
    return datetime.datetime(
        date.year,
        date.month,
        date.day,
    )
