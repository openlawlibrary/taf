import datetime
from pathlib import Path
import shutil
import uuid
from freezegun import freeze_time
from taf.api.repository import create_repository
from taf.api.utils._metadata import (
    update_snapshot_and_timestamp,
    update_target_metadata,
)
from taf.auth_repo import AuthenticationRepository
from pytest import fixture
from taf.tests.conftest import CLIENT_DIR_PATH
from taf.tests.test_api.util import check_if_targets_removed, check_if_targets_signed
from taf.utils import on_rm_error
from tuf.repository_tool import TARGETS_DIRECTORY_NAME


AUTH_REPO_NAME = "auth"

TARGET_FILE1 = "test1.txt"
TARGET_FILE2 = "test2.txt"
TARGET_FILE3 = "test3.txt"


@fixture(scope="module")
def auth_repo_path():
    random_name = str(uuid.uuid4())
    root_dir = CLIENT_DIR_PATH / random_name
    auth_path = root_dir / AUTH_REPO_NAME
    auth_path.mkdir(exist_ok=True, parents=True)
    yield auth_path
    shutil.rmtree(root_dir, onerror=on_rm_error)


def test_create_repository_with_targets(
    auth_repo_path: Path, no_yubikeys_path: str, api_keystore: str
):
    repo_path = str(auth_repo_path)
    # add a new file to the targets directory, check if it was signed
    targets_dir = auth_repo_path / TARGETS_DIRECTORY_NAME
    targets_dir.mkdir()
    file_path = targets_dir / TARGET_FILE1
    file_path.write_text("test1")
    file_path = targets_dir / TARGET_FILE2
    file_path.write_text("test2")
    create_repository(
        repo_path,
        roles_key_infos=no_yubikeys_path,
        keystore=api_keystore,
        commit=True,
    )


@freeze_time("2023-01-01")
def test_update_snapshot_and_timestamp(auth_repo_path: Path, api_keystore: str):
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


def test_update_target_metadata(auth_repo_path: Path, api_keystore: str):
    auth_repo = AuthenticationRepository(path=auth_repo_path)
    # remove one file, add one file, modify one file
    # add a new file to the targets directory, check if it was signed
    target_path1 = auth_repo_path / TARGETS_DIRECTORY_NAME / TARGET_FILE1
    target_path1.write_text("updated")
    target_path2 = auth_repo_path / TARGETS_DIRECTORY_NAME / TARGET_FILE2
    target_path2.unlink()
    target_path3 = auth_repo_path / TARGETS_DIRECTORY_NAME / TARGET_FILE3
    target_path3.write_text("test3")

    added_targets_data, removed_targets_data = auth_repo.get_all_target_files_state()
    assert TARGET_FILE1 in added_targets_data
    assert TARGET_FILE2 in removed_targets_data
    assert TARGET_FILE3 in added_targets_data
    assert TARGET_FILE1 not in removed_targets_data
    assert TARGET_FILE2 not in added_targets_data
    assert TARGET_FILE3 not in removed_targets_data
    update_target_metadata(
        auth_repo,
        added_targets_data=added_targets_data,
        removed_targets_data=removed_targets_data,
        keystore=api_keystore,
        write=True,
    )
    check_if_targets_signed(auth_repo, "targets", TARGET_FILE1, TARGET_FILE3)
    check_if_targets_removed(auth_repo, TARGET_FILE2)
