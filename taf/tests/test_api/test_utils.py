import datetime
import shutil
import uuid
from freezegun import freeze_time
from taf.api.repository import create_repository
from taf.api.utils.metadata_utils import update_snapshot_and_timestamp
from taf.auth_repo import AuthenticationRepository
from pytest import fixture
from taf.tests.conftest import CLIENT_DIR_PATH
from taf.utils import on_rm_error


AUTH_REPO_NAME = "auth"


@fixture(scope="module")
def auth_repo_path():
    random_name = str(uuid.uuid4())
    root_dir = CLIENT_DIR_PATH / random_name
    auth_path = root_dir / AUTH_REPO_NAME
    auth_path.mkdir(exist_ok=True, parents=True)
    yield auth_path
    shutil.rmtree(root_dir, onerror=on_rm_error)


def test_create_repository(auth_repo_path, no_yubikeys_path, api_keystore):
    repo_path = str(auth_repo_path)
    create_repository(
        repo_path,
        roles_key_infos=no_yubikeys_path,
        keystore=api_keystore,
        commit=True,
    )


@freeze_time("2023-01-01")
def test_update_snapshot_and_timestamp(auth_repo_path, api_keystore):
    auth_repo = AuthenticationRepository(path=auth_repo_path)
    # signs snapshot and timestamp, uses default expiration intervals
    update_snapshot_and_timestamp(
        auth_repo,
        keystore=api_keystore,
    )
    now = datetime.datetime.now()
    for role, interval in [("timestamp", 1), ("snapshot", 7)]:
        actual_expiration = auth_repo.get_expiration_date(role)
        assert now + datetime.timedelta(interval) == actual_expiration
