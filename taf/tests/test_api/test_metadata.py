import datetime
import shutil
import uuid
from freezegun import freeze_time
from pathlib import Path
from taf.messages import git_commit_message
from taf.auth_repo import AuthenticationRepository
from taf.git import GitRepository
from pytest import fixture
from taf.api.repository import create_repository
from taf.tests.conftest import CLIENT_DIR_PATH
from taf.utils import on_rm_error
from taf.api.metadata import check_expiration_dates


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
    auth_repo_path,
    with_delegations_no_yubikeys_path,
    api_keystore,
):

    create_repository(
        str(auth_repo_path),
        roles_key_infos=with_delegations_no_yubikeys_path,
        keystore=api_keystore,
        commit=True,
    )


@freeze_time("2023-01-01")
def test_check_expiration_date_when_all_expired(auth_repo_path):
    expired, will_expire = check_expiration_dates(auth_repo_path, print=False)
    # expect expire after 1 day
    start = datetime.datetime(2021, 12, 31)
    _check_expired_role("timestamp", start, 1, expired)
    _check_expired_role("snapshot", start, 7, expired)
    # expect expire afer 90 days
    for target_role in ("targets", "delegated_role", "inner_role"):
        _check_expired_role(target_role, start, 91, expired)
    _check_expired_role("root", start, 365, expired)


def _check_expired_role(role_name, start_time, interval, expired_dict):
    assert role_name in expired_dict
    expected_expiration_date = start_time + datetime.timedelta(days=interval)
    actual_expiration_time = expired_dict[role_name]
    # strip hours and minutes, they are set in case of targets and root
    actual_expiration_date = datetime.datetime(
        actual_expiration_time.year,
        actual_expiration_time.month,
        actual_expiration_time.day,
    )
    assert expected_expiration_date == actual_expiration_date
