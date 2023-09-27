import shutil
import uuid
from pytest import fixture
from taf.api.repository import create_repository
from taf.api.targets import add_target_repo
from taf.tests.conftest import CLIENT_DIR_PATH
from taf.tests.test_api.util import copy_mirrors_json, copy_repositories_json
from taf.updater.updater import validate_repository
from taf.utils import on_rm_error
from tuf.repository_tool import METADATA_DIRECTORY_NAME, TARGETS_DIRECTORY_NAME


@fixture(scope="module")
def auth_repo_path():
    random_name = str(uuid.uuid4())
    path = CLIENT_DIR_PATH / random_name / "auth"
    yield path
    shutil.rmtree(path.parent, onerror=on_rm_error)


def test_setup_auth_repo_when_add_repositories_json(
    auth_repo_path,
    with_delegations_no_yubikeys_path,
    api_keystore,
    repositories_json_template,
    mirrors_json_path,
):
    repo_path = str(auth_repo_path)
    namespace = auth_repo_path.parent.name
    copy_repositories_json(repositories_json_template, namespace, auth_repo_path)
    copy_mirrors_json(mirrors_json_path, namespace, auth_repo_path)

    create_repository(
        repo_path,
        roles_key_infos=with_delegations_no_yubikeys_path,
        keystore=api_keystore,
        commit=True,
        commit_msg="Initial commit",
    )


def test_add_target_repository_when_not_on_filesystem(auth_repo_path, api_keystore):
    path = str(auth_repo_path)
    namespace = auth_repo_path.parent.name
    add_target_repo(
        path,
        None,
        f"{namespace}/target4",
        "delegated_role",
        None,
        api_keystore,
        commit_msg="Add new target repository",
        push=False,
    )
