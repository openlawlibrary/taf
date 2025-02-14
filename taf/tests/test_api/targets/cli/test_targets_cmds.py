import json
from pathlib import Path

from click.testing import CliRunner

from taf.constants import TARGETS_DIRECTORY_NAME
from taf.tests.test_api.util import check_if_targets_signed
from taf.tools.cli.taf import taf


def test_targets_sign_when_target_file_is_added_expect_success(
    auth_repo_when_add_repositories_json,
    library,
    keystore_delegations,
):
    runner = CliRunner()

    repo_path = library / "auth"
    FILENAME = "test.txt"
    file_path = repo_path / TARGETS_DIRECTORY_NAME / FILENAME
    file_path.write_text("test")

    runner.invoke(
        taf,
        [
            "targets",
            "sign",
            "--path",
            f"{str(auth_repo_when_add_repositories_json.path)}",
            "--keystore",
            f"{str(keystore_delegations)}",
        ],
    )

    check_if_targets_signed(auth_repo_when_add_repositories_json, "targets", FILENAME)


def test_targets_sign_when_target_file_is_removed_expect_success(
    auth_repo_when_add_repositories_json,
    library,
    keystore_delegations,
):
    runner = CliRunner()

    repo_path = library / "auth"
    FILENAME = "test.txt"
    file_path = repo_path / TARGETS_DIRECTORY_NAME / FILENAME
    file_path.write_text("test")

    runner.invoke(
        taf,
        [
            "targets",
            "sign",
            "--path",
            f"{str(auth_repo_when_add_repositories_json.path)}",
            "--keystore",
            f"{str(keystore_delegations)}",
        ],
    )
    check_if_targets_signed(auth_repo_when_add_repositories_json, "targets", FILENAME)

    file_path.unlink()

    runner.invoke(
        taf,
        [
            "targets",
            "sign",
            "--path",
            f"{str(auth_repo_when_add_repositories_json.path)}",
            "--keystore",
            f"{str(keystore_delegations)}",
        ],
    )

    signed_target_files = auth_repo_when_add_repositories_json.get_signed_target_files()
    assert FILENAME not in signed_target_files


def test_targets_add_repo_cmd_expect_success(
    auth_repo_when_add_repositories_json, library, keystore_delegations
):
    runner = CliRunner()

    namespace = library.name
    target_repo_name = f"{namespace}/target4"

    with runner.isolated_filesystem():
        # cli expects a config file, so we manually create config pass it to the cli
        cwd = Path.cwd()
        config = {
            "allow-unauthenticated-commits": True,
            "type": "html",
            "serve": "latest",
            "location_regex": "/",
            "routes": [".*"],
        }
        config_file_path = cwd / "config.json"
        with open(config_file_path, "w") as f:
            json.dump(config, f)

        runner.invoke(
            taf,
            [
                "targets",
                "add-repo",
                f"{target_repo_name}",
                "--role",
                "delegated_role",
                "--path",
                f"{str(auth_repo_when_add_repositories_json.path)}",
                "--custom-file",
                f"{str(config_file_path)}",
                "--keystore",
                f"{str(keystore_delegations)}",
            ],
        )
        delegated_paths = auth_repo_when_add_repositories_json.get_paths_of_role(
            "delegated_role"
        )
        assert target_repo_name in delegated_paths


def test_targets_remove_repo_cmd_expect_success():
    # TODO: seems like it is not fully supported yet
    pass
