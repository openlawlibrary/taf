import json

from click.testing import CliRunner

from taf.api.repository import create_repository
from taf.auth_repo import AuthenticationRepository
from taf.tests.test_api.conftest import DEPENDENCY_NAME
from taf.tools.cli.taf import taf


def test_dependencies_add_cmd_expect_success(
    parent_repo_path,
    child_repo_path,
    with_delegations_no_yubikeys_path,
    keystore_delegations,
):
    for path in (child_repo_path, parent_repo_path):
        create_repository(
            str(path),
            roles_key_infos=with_delegations_no_yubikeys_path,
            keystore=keystore_delegations,
            commit=True,
        )
    runner = CliRunner()

    parent_auth_repo = AuthenticationRepository(path=parent_repo_path)
    child_auth_repo = AuthenticationRepository(path=child_repo_path)

    assert not (parent_auth_repo.path / "targets" / "dependencies.json").exists()

    runner.invoke(
        taf,
        [
            "dependencies",
            "add",
            DEPENDENCY_NAME,
            "--path",
            f"{str(parent_auth_repo.path)}",
            "--dependency-path",
            f"{child_auth_repo.path}",
            "--keystore",
            f"{str(keystore_delegations)}",
        ],
        input="y\n",  # pass in y to resolve Proceed? prompt
    )
    assert (parent_auth_repo.path / "targets" / "dependencies.json").exists()

    dependencies_json = json.loads(
        (parent_auth_repo.path / "targets" / "dependencies.json").read_text()
    )
    dependencies = dependencies_json["dependencies"][DEPENDENCY_NAME]
    assert (
        child_auth_repo.head_commit_sha() in dependencies["out-of-band-authentication"]
    )
    assert child_auth_repo.default_branch in dependencies["branch"]


def test_dependencies_remove_cmd_expect_success(
    parent_repo_path,
    keystore_delegations,
):
    runner = CliRunner()

    parent_auth_repo = AuthenticationRepository(path=parent_repo_path)

    runner.invoke(
        taf,
        [
            "dependencies",
            "remove",
            DEPENDENCY_NAME,
            "--path",
            f"{str(parent_auth_repo.path)}",
            "--keystore",
            f"{str(keystore_delegations)}",
        ],
    )
    dependencies_json = json.loads(
        (parent_auth_repo.path / "targets" / "dependencies.json").read_text()
    )
    assert DEPENDENCY_NAME not in dependencies_json["dependencies"].keys()
