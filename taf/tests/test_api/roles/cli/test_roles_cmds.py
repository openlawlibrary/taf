from pathlib import Path

from click.testing import CliRunner

from taf.api.roles import list_keys_of_role
from taf.tests.test_api.conftest import ADD_ROLES_CONFIG_INPUT
from taf.tests.test_api.util import check_new_role
from taf.tools.cli.taf import taf


def test_roles_add_cmd_expect_success(auth_repo, roles_keystore):
    runner = CliRunner()

    with runner.isolated_filesystem():
        runner.invoke(
            taf,
            [
                "roles",
                "add",
                "--config-file",
                f"{ADD_ROLES_CONFIG_INPUT}",
                "--path",
                f"{str(auth_repo.path)}",
                "--keystore",
                f"{str(roles_keystore)}",
            ],
        )
        new_roles = ["delegated_role"]
        target_roles = auth_repo.get_all_targets_roles()
        for role_name in new_roles:
            assert role_name in target_roles
        assert auth_repo.find_delegated_roles_parent("delegated_role") == "targets"
        check_new_role(
            auth_repo,
            "delegated_role",
            ["/delegated_path_inside_targets1", "/delegated_path_inside_targets2"],
            str(roles_keystore),
            "targets",
        )


def test_roles_add_role_paths_cmd_expect_success(
    auth_repo_with_delegations, roles_keystore
):
    runner = CliRunner()

    with runner.isolated_filesystem():
        new_paths = ["some-path3"]
        role_name = "delegated_role"
        runner.invoke(
            taf,
            [
                "roles",
                "add-role-paths",
                f"{role_name}",
                "--path",
                f"{str(auth_repo_with_delegations.path)}",
                "--delegated-path",
                f"{new_paths[0]}",
                "--keystore",
                f"{str(roles_keystore)}",
            ],
        )
        roles_paths = auth_repo_with_delegations.get_role_paths(role_name)
        assert len(roles_paths) == 3
        assert "some-path3" in roles_paths


def test_roles_add_signing_key_cmd_expect_success(auth_repo, roles_keystore):
    runner = CliRunner()

    with runner.isolated_filesystem():
        pub_key_path = Path(roles_keystore, "targets1.pub")
        runner.invoke(
            taf,
            [
                "roles",
                "add-signing-key",
                "--path",
                f"{str(auth_repo.path)}",
                "--role",
                "snapshot",
                "--role",
                "timestamp",
                "--pub-key-path",
                f"{pub_key_path}",
                "--keystore",
                f"{str(roles_keystore)}",
                "--no-commit",
            ],
        )
        timestamp_keys_infos = list_keys_of_role(str(auth_repo.path), "timestamp")
        assert len(timestamp_keys_infos) == 2
        snapshot_keys_infos = list_keys_of_role(str(auth_repo.path), "snapshot")
        assert len(snapshot_keys_infos) == 2


def test_revoke_key_cmd_expect_success(auth_repo, roles_keystore):
    runner = CliRunner()

    targets_keys_infos = list_keys_of_role(str(auth_repo.path), "targets")
    assert len(targets_keys_infos) == 2

    with runner.isolated_filesystem():
        targest_keyids = auth_repo.get_keyids_of_role("targets")
        key_to_remove = targest_keyids[-1]
        runner.invoke(
            taf,
            [
                "roles",
                "revoke-key",
                f"{key_to_remove}",
                "--path",
                f"{str(auth_repo.path)}",
                "--keystore",
                f"{str(roles_keystore)}",
                "--no-commit",
            ],
        )
        targets_keys_infos = list_keys_of_role(str(auth_repo.path), "targets")
        assert len(targets_keys_infos) == 1
        # reset to head so that next test can run as expected
        auth_repo.reset_to_head()


def test_rotate_key_cmd_expect_success(auth_repo, roles_keystore):
    runner = CliRunner()

    with runner.isolated_filesystem():
        targest_keyids = auth_repo.get_keyids_of_role("targets")
        key_to_rotate = targest_keyids[-1]
        pub_key_path = Path(roles_keystore, "delegated_role1.pub")

        assert len(targest_keyids) == 2

        runner.invoke(
            taf,
            [
                "roles",
                "rotate-key",
                f"{key_to_rotate}",
                "--path",
                f"{str(auth_repo.path)}",
                "--pub-key-path",
                f"{pub_key_path}",
                "--keystore",
                f"{str(roles_keystore)}",
                "--revoke-commit-msg",
                "Remove targets key",
                "--add-commit-msg",
                "Add signing key",
            ],
        )
        new_targets_keyids = auth_repo.get_keyids_of_role("targets")

        assert len(new_targets_keyids) == 2
        # TODO: this assert does not pass. I assumed that the rotated key would not be in targets keyids,
        # but I might have misunderstood what I needed to assert
        assert key_to_rotate not in new_targets_keyids
