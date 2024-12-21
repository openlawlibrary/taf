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
                ".\\test-law\\",
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
        assert (cwd / "test-law" / "metadata").exists()
        assert (cwd / "test-law" / "targets").exists()
        # TODO: actually have this. hopefully once issue is resolved error should get removed from assert
        assert "An error occurred while signing target files" in output
        assert "An error occurred while creating a new repository" in output


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
                ".\\test-law\\",
                "--keys-description",
                f"{str(with_delegations_no_yubikeys_path)}",
                "--keystore",
                f"{str(keystore_delegations)}",
                "--no-commit",
                "--test",
            ],
        )
        cwd = Path.cwd()
        assert (cwd / "test-law" / "metadata").exists()
        assert (cwd / "test-law" / "targets").exists()

        output = caplog.text
        assert "Finished creating a new repository" in output
        # run the same command again
        result = runner.invoke(
            taf,
            [
                "repo",
                "create",
                ".\\test-law\\",
                "--keys-description",
                f"{str(with_delegations_no_yubikeys_path)}",
                "--keystore",
                f"{str(keystore_delegations)}",
                "--no-commit",
                "--test",
            ],
        )
        # TODO: expected to have this output, instead get same error as first test
        assert (
            '"test-law" is a git repository containing the metadata directory. Generating new metadata files could make the repository invalid. Aborting'
            in result.output
        )
