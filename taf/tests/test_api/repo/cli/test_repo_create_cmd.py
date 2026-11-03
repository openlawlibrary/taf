import json
import os
from pathlib import Path

from click.testing import CliRunner

from taf.tools.cli.taf import taf


def test_repo_create_cmd_expect_success(
    keystore_delegations, with_delegations_no_yubikeys_path, caplog
):
    runner = CliRunner()
    with runner.isolated_filesystem():
        result = runner.invoke(
            taf,
            [
                "repo",
                "create",
                "test/law",
                "--keys-description",
                f"{str(with_delegations_no_yubikeys_path)}",
                "--keystore",
                f"{str(keystore_delegations)}",
                "--no-commit",
                "--test",
            ],
        )
        # logging statements are captured by caplog
        # while print statements are captured by pytest CliRunner result object
        output = caplog.text
        # TODO: expected to have these asserts
        assert "Please commit manually" in result.output
        assert "Finished creating a new repository" in output

        cwd = Path.cwd()
        assert (cwd / "test/law" / "metadata").exists()
        assert (cwd / "test/law" / "targets").exists()


def test_repo_create_cmd_uses_keystore_from_keys_description_over_found_keystore(
    keystore_delegations, with_delegations_no_yubikeys_path
):
    runner = CliRunner()
    with runner.isolated_filesystem():
        found_keystore = Path(".taf/keystore")
        found_keystore.mkdir(parents=True)
        keys_description = json.loads(
            Path(with_delegations_no_yubikeys_path).read_text()
        )
        keys_description["keystore"] = str(keystore_delegations)

        runner.invoke(
            taf,
            [
                "repo",
                "create",
                "test/law",
                "--keys-description",
                json.dumps(keys_description),
                "--no-commit",
            ],
        )

        assert (Path("test/law") / "metadata").exists()
        assert not any(found_keystore.iterdir())


def test_repo_create_cmd_when_it_fails_keeps_existing_directory(keystore_delegations):
    runner = CliRunner()
    with runner.isolated_filesystem():
        repositories_json = Path("test/law/targets/repositories.json")
        repositories_json.parent.mkdir(parents=True)
        repositories_json.write_text("{}")

        runner.invoke(
            taf,
            [
                "repo",
                "create",
                "test/law",
                "--keys-description",
                "not a keys description",
                "--keystore",
                f"{str(keystore_delegations)}",
                "--no-commit",
            ],
        )

        assert not (Path("test/law") / "metadata").exists()
        assert repositories_json.exists()


def test_repo_create_cmd_when_repo_already_created_expect_error(
    keystore_delegations, with_delegations_no_yubikeys_path, caplog
):
    runner = CliRunner()
    with runner.isolated_filesystem():
        result = runner.invoke(
            taf,
            [
                "repo",
                "create",
                "test/law",
                "--keys-description",
                f"{str(with_delegations_no_yubikeys_path)}",
                "--keystore",
                f"{str(keystore_delegations)}",
                "--no-commit",
                "--test",
            ],
        )
        cwd = Path.cwd()
        assert (cwd / "test/law" / "metadata").exists()
        assert (cwd / "test/law" / "targets").exists()

        output = caplog.text
        assert "Finished creating a new repository" in output
        # run the same command again
        result = runner.invoke(
            taf,
            [
                "repo",
                "create",
                "test/law",
                "--keys-description",
                f"{str(with_delegations_no_yubikeys_path)}",
                "--keystore",
                f"{str(keystore_delegations)}",
                "--no-commit",
                "--test",
            ],
        )
        assert (
            f'Metadata directory found inside "test{os.sep}law". Recreate metadata files? [y/N]'
            in result.output
        )
