from click.testing import CliRunner

from taf.tools.cli.taf import taf


def test_repo_validate_cmd_when_it_fails_keeps_uncommitted_metadata_changes(
    auth_repo,
):
    targets_metadata = auth_repo.path / "metadata" / "targets.json"
    edited = targets_metadata.read_text() + "\n"
    targets_metadata.write_text(edited)

    result = CliRunner().invoke(
        taf,
        ["repo", "validate", "--path", str(auth_repo.path), "--from-commit", "0" * 40],
    )

    assert result.exit_code != 0
    assert targets_metadata.read_text() == edited
