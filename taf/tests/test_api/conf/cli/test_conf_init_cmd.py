from pathlib import Path

from click.testing import CliRunner

from taf.tools.cli.taf import taf


def test_init_conf_cmd_expect_success(keystore):
    runner = CliRunner()
    with runner.isolated_filesystem():
        cwd = Path.cwd()
        runner.invoke(
            taf,
            [
                "conf",
                "init",
                "--keystore",
                f"{str(keystore)}",
            ],
        )
        assert (cwd / ".taf" / "config.toml").exists()
        assert (cwd / ".taf" / "keystore").exists()
