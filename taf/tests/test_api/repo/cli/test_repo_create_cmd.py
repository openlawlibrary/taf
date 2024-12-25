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
