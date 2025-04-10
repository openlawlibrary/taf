import json
from pathlib import Path
import click
from taf.api.roles import (
    add_roles as add_multiple_roles,
    list_keys_of_role,
    add_signing_key,
    remove_role,
    revoke_signing_key,
    remove_paths,
    rotate_signing_key,
)
from taf.constants import DEFAULT_RSA_SIGNATURE_SCHEME
from taf.exceptions import TAFError
from taf.auth_repo import AuthenticationRepository
from taf.log import taf_logger
from taf.tools.cli import catch_cli_exception, common_repo_edit_options, find_repository

from taf.api.roles import add_role_paths
from taf.tools.repo import pin_managed


def add_roles_command():
    @click.command(help="""
    Add new delegated target roles. Allows optional specification of each role's properties through a JSON configuration file.

    Configuration file (JSON) can specify:
    - 'parent_role' (string): The parent role under which the new role will be delegated. Default is 'targets'.
    - 'delegated_path' (array of strings): Paths to be delegated to the new role. Must specify at least one if using a config file.
    - 'keys_number' (integer): Number of signing keys. Default is 1.
    - 'threshold' (integer): Number of keys required to sign. Default is 1.
    - 'yubikey' (boolean): Whether to use a YubiKey for signing. Default is false.
    - 'scheme' (string): Signature scheme, e.g., 'rsa-pkcs1v15-sha256'. Default is 'rsa-pkcs1v15-sha256'.

    The structure of the configuration file is the very similar tohe structure of the one use when creating the repository,
    but does not have to contain all roles, just the ones that should be added. If roles that already
    exist are also defined, they will be skipped. If the role's parent is not the main targets role,
    it's necessary to specify it using the "parent_role" option

    Example JSON structure:
    {
    "yubikeys": {
        "user1": {
        "public": "<public_key>",
        "scheme": "rsa-pkcs1v15-sha256",
        "present": false
        },
        "userYK": {
        "scheme": "rsa-pkcs1v15-sha256"
        }
    },
    "roles": {
        "<role name>": {
        "parent_role": "targets",
        "paths": [
            "</delegated_path_inside_targets1>",
            "</delegated_path_inside_targets2>"
        ],
        "number": 2,
        "threshold": 1,
        "yubikey": true,
        "scheme": "rsa-pkcs1v15-sha256",
        "yubikeys": [
            "user1",
            "userYK"
        ]
        }
    }
    }
    """)
    @find_repository
    @catch_cli_exception(handle=TAFError)
    @common_repo_edit_options
    @click.option("--config-file", type=click.Path(exists=True), help="Path to the JSON configuration file.")
    @click.option("--path", default=".", help="Authentication repository's location. If not specified, set to the current directory")
    @click.option("--scheme", default=DEFAULT_RSA_SIGNATURE_SCHEME, help="A signature scheme used for signing")
    @pin_managed
    def add_roles(config_file, path, scheme, keystore, no_commit, prompt_for_keys, pin_manager, keys_description, no_remote_check):
        add_multiple_roles(
            path=path,
            pin_manager=pin_manager,
            keystore=keystore,
            roles_key_infos=config_file,
            scheme=scheme,
            prompt_for_keys=prompt_for_keys,
            commit=not no_commit,
            keys_description=keys_description,
            skip_remote_check=no_remote_check,
        )
    return add_roles


def export_roles_description_command():
    @click.command(help="""
        Export roles-description.json file based on the
        """)
    @find_repository
    @catch_cli_exception(handle=TAFError)
    @click.option("--path", default=".", help="Authentication repository's location. If not specified, set to the current directory")
    @click.option("--output", default=None, help="Output file path")
    @click.option("--keystore", default=None, help="Location of the keystore files")
    @pin_managed
    def export_roles_description(path, output, keystore, pin_manager):
        auth_repo = AuthenticationRepository(path=path, pin_manager=pin_manager)
        roles_description = auth_repo.generate_roles_description()
        if keystore:
            roles_description["keystore"] = keystore
        if not output:
            taf_logger.log("NOTICE", json.dumps(roles_description, indent=True))
        else:
            output = Path(output)
            output.parent.mkdir(exist_ok=True, parents=True)
            output.write_text(json.dumps(roles_description, indent=True))

    return export_roles_description


def add_role_paths_command():
    @click.command(help="Add a new delegated target role, specifying which paths are delegated to the new role. Its parent role, number of signing keys and signatures threshold can also be defined. Update and sign all metadata files and commit.")
    @find_repository
    @catch_cli_exception(handle=TAFError)
    @click.argument("role")
    @common_repo_edit_options
    @click.option("--path", default=".", help="Authentication repository's location. If not specified, set to the current directory")
    @click.option("--delegated-path", multiple=True, help="Paths associated with the delegated role")
    @pin_managed
    def adding_role_paths(role, path, delegated_path, keystore, no_commit, prompt_for_keys, pin_manager, keys_description, no_remote_check):
        if not delegated_path:
            print("Specify at least one path")
            return

        add_role_paths(
            path=path,
            paths=delegated_path,
            pin_manager=pin_manager,
            delegated_role=role,
            keystore=keystore,
            commit=not no_commit,
            prompt_for_keys=prompt_for_keys,
            push=not no_commit,
            keys_description=keys_description,
            skip_remote_check=no_remote_check,
        )
    return adding_role_paths


# commenting out this command since its execution leads to an invalid state
# this is a TUF bug (or better said, caused by using a newer version of the updater and old repository_tool)
# it will be addressed when we transition to metadata API
def remove_role_command():
    @click.command(help="""Remove a delegated target role, and, optionally, its targets (depending on the remove-targets parameter).
        If targets should also be deleted, target files are remove and their corresponding entires are removed
        from repositoires.json. If targets should not get removed, the target files are signed using the
        removed role's parent role
        """)
    @find_repository
    @catch_cli_exception(handle=TAFError)
    @click.argument("role")
    @common_repo_edit_options
    @click.option("--path", default=".", help="Authentication repository's location. If not specified, set to the current directory")
    @click.option("--scheme", default=DEFAULT_RSA_SIGNATURE_SCHEME, help="A signature scheme used for signing")
    @click.option("--remove-targets/--no-remove-targets", default=True, help="Should targets delegated to this role also be removed. If not removed, they are signed by the parent role")
    @pin_managed
    def remove(role, path, keystore, scheme, remove_targets, no_commit, prompt_for_keys, pin_manager, keys_description, no_remote_check):
        remove_role(
            path=path,
            pin_manager=pin_manager,
            role=role,
            keystore=keystore,
            scheme=scheme,
            remove_targets=remove_targets,
            commit=not no_commit,
            prompt_for_keys=prompt_for_keys,
            keys_description=keys_description,
            skip_remote_check=no_remote_check,
        )
    return remove


def remove_paths_command():
    @click.command(help="""Remove paths from delegated role""")
    @find_repository
    @catch_cli_exception(handle=TAFError)
    @common_repo_edit_options
    @click.option("--path", default=".", help="Authentication repository's location. If not specified, set to the current directory")
    @click.option("--delegated-path", multiple=True, help="A list of paths to be removed")
    @click.option("--scheme", default=DEFAULT_RSA_SIGNATURE_SCHEME, help="A signature scheme used for signing")
    @click.option("--commit-msg", default=None, help="Commit message")
    @pin_managed
    def remove_delegated_paths(path, delegated_path, keystore, scheme, no_commit, prompt_for_keys, pin_manager, keys_description, no_remote_check, commit_msg):
        if not delegated_path:
            print("Specify at least one role")
            return

        remove_paths(
            path=path,
            pin_manager=pin_manager,
            paths=delegated_path,
            keystore=keystore,
            scheme=scheme,
            commit=not no_commit,
            prompt_for_keys=prompt_for_keys,
            keys_description=keys_description,
            skip_remote_check=no_remote_check,
            commit_msg=commit_msg,
        )
    return remove_delegated_paths


def add_signing_key_command():
    @click.command(help="""
        Add a new signing key. This will make it possible to a sign metadata files
        corresponding to the specified roles with another key. Although private keys are
        used for signing, key identifiers are calculated based on the public keys. This
        means that it's necessary to enter the public key in order to register
        a new signing key. Public key can be loaded from a file, in which case it is
        necessary to specify its path as the pub_key parameter's value. If this option
        is not used when calling this command, the key can be directly entered later.
        """)
    @find_repository
    @catch_cli_exception(handle=TAFError)
    @common_repo_edit_options
    @click.option("--path", default=".", help="Authentication repository's location. If not specified, set to the current directory")
    @click.option("--role", multiple=True, help="A list of roles to whose list of signing keys the new key should be added")
    @click.option("--pub-key-path", default=None, help="Path to the public key corresponding to the private key which should be registered as the role's signing key")
    @click.option("--scheme", default=DEFAULT_RSA_SIGNATURE_SCHEME, help="A signature scheme used for signing")
    @click.option("--commit-msg", default=None, help="Commit message")
    @pin_managed
    def adding_signing_key(path, role, pub_key_path, keystore, scheme, no_commit, prompt_for_keys, pin_manager, keys_description, no_remote_check, commit_msg):
        if not role:
            print("Specify at least one role")
            return

        add_signing_key(
            path=path,
            pin_manager=pin_manager,
            roles=role,
            pub_key_path=pub_key_path,
            keystore=keystore,
            scheme=scheme,
            commit=not no_commit,
            prompt_for_keys=prompt_for_keys,
            keys_description=keys_description,
            skip_remote_check=no_remote_check,
            commit_msg=commit_msg,
        )
    return adding_signing_key


def revoke_signing_key_command():
    @click.command(help="""
        Revoke a signing key.
        """)
    @find_repository
    @catch_cli_exception(handle=TAFError)
    @common_repo_edit_options
    @click.argument("keyid")
    @click.option("--path", default=".", help="Authentication repository's location. If not specified, set to the current directory")
    @click.option("--role", multiple=True, help="A list of roles from which to remove the key. If unspecified, the key is removed from all roles by default.")
    @click.option("--scheme", default=DEFAULT_RSA_SIGNATURE_SCHEME, help="A signature scheme used for signing")
    @click.option("--commit-msg", default=None, help="Commit message")
    @pin_managed
    def revoke_key(path, role, keyid, keystore, scheme, no_commit, prompt_for_keys, pin_manager, keys_description, no_remote_check, commit_msg):

        revoke_signing_key(
            path=path,
            pin_manager=pin_manager,
            roles=role,
            key_id=keyid,
            keystore=keystore,
            scheme=scheme,
            commit=not no_commit,
            prompt_for_keys=prompt_for_keys,
            keys_description=keys_description,
            skip_remote_check=no_remote_check,
            commit_msg=commit_msg,
        )
    return revoke_key


def rotate_signing_key_command():
    @click.command(help="""
        Rotate a signing key.
        """)
    @find_repository
    @catch_cli_exception(handle=TAFError)
    @click.argument("keyid")
    @click.option("--path", default=".", help="Authentication repository's location. If not specified, set to the current directory")
    @click.option("--role", multiple=True, help="A list of roles from which to rotate the key. Rotate from all by default")
    @click.option("--pub-key-path", default=None, help="Path to the public key corresponding to the private key which should be registered as the role's signing key")
    @click.option("--scheme", default=DEFAULT_RSA_SIGNATURE_SCHEME, help="A signature scheme used for signing")
    @click.option("--revoke-commit-msg", default=None, help="Revoke key commit message")
    @click.option("--add-commit-msg", default=None, help="Add new signing key commit message")
    @common_repo_edit_options
    @pin_managed
    def rotate_key(path, role, keyid, pub_key_path, keystore, scheme, prompt_for_keys, revoke_commit_msg, add_commit_msg, pin_manager, keys_description, no_remote_check, no_commit):
        rotate_signing_key(
            path=path,
            pin_manager=pin_manager,
            roles=role,
            key_id=keyid,
            keystore=keystore,
            scheme=scheme,
            prompt_for_keys=prompt_for_keys,
            pub_key_path=pub_key_path,
            revoke_commit_msg=revoke_commit_msg,
            add_commit_msg=add_commit_msg,
            keys_description=keys_description,
            skip_remote_check=no_remote_check,
            commit=not no_commit
        )
    return rotate_key


def list_keys_command():
    @click.command(help="""
        List all keys of the specified role. If certs directory exists and contains certificates exported from YubiKeys,
        include additional information read from these certificates, like name or organization.
        """)
    @find_repository
    @catch_cli_exception(handle=TAFError)
    @click.argument("role")
    @click.option("--path", default=".", help="Authentication repository's location. If not specified, set to the current directory")
    def list_keys(role, path):
        key_infos = list_keys_of_role(
            path=path,
            role=role,
        )
        print("\n".join(key_infos))
    return list_keys


def attach_to_group(group):

    group.add_command(add_roles_command(), name='add')
    group.add_command(add_role_paths_command(), name='add-role-paths')
    group.add_command(remove_paths_command(), name='remove-paths')
    # group.add_command(remove_role_command(), name='remove')
    group.add_command(add_signing_key_command(), name='add-signing-key')
    group.add_command(revoke_signing_key_command(), name='revoke-key')
    group.add_command(rotate_signing_key_command(), name='rotate-key')
    group.add_command(list_keys_command(), name='list-keys')
    group.add_command(export_roles_description_command(), name="export-description")
