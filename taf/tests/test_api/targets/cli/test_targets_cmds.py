import json
from pathlib import Path

from click.testing import CliRunner

from taf.api.targets import update_target_repos_from_repositories_json
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


def _signed_target_repositories(library, pin_manager, keystore_delegations):
    update_target_repos_from_repositories_json(
        str(library / "auth"),
        pin_manager,
        str(library.parent),
        keystore_delegations,
        push=False,
    )


def test_targets_list_prints_each_target_repository_and_its_state(
    auth_repo_when_add_repositories_json,
    pin_manager,
    library,
    keystore_delegations,
):
    _signed_target_repositories(library, pin_manager, keystore_delegations)

    result = CliRunner().invoke(
        taf, ["targets", "list", "--path", str(library / "auth")]
    )

    assert result.exit_code == 0
    lines = result.output.splitlines()
    for name in ("target1", "target2", "target3"):
        start = lines.index(f"Target repository: {library.name}/{name}")
        assert lines[start + 1 : start + 3] == ["  Cloned: yes", "  Bare: no"]


def test_repo_status_prints_the_repository_and_its_target_repositories(
    auth_repo_when_add_repositories_json,
    pin_manager,
    library,
    keystore_delegations,
):
    _signed_target_repositories(library, pin_manager, keystore_delegations)
    auth_path = library / "auth"

    result = CliRunner().invoke(taf, ["repo", "status", "--path", str(auth_path)])

    assert result.exit_code == 0
    lines = result.output.splitlines()
    assert lines[:2] == [
        f"Authentication repository: {library.name}/auth",
        f"  Path: {auth_path.resolve()}",
    ]
    # the repository was created locally and was never pushed
    assert "  Up to date: no remote" in lines
    for name in ("target1", "target2", "target3"):
        assert f"  Target repository: {library.name}/{name}" in lines
