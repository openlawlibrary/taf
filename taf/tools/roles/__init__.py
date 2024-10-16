import json
from pathlib import Path
import sys
import click
from taf.api.roles import add_multiple_roles, add_role, list_keys_of_role, add_signing_key, remove_role
from taf.constants import DEFAULT_RSA_SIGNATURE_SCHEME
from taf.exceptions import TAFError
from taf.auth_repo import AuthenticationRepository
from taf.log import taf_logger
from taf.tools.cli import catch_cli_exception, find_repository

from taf.api.roles import add_role_paths


def add_role_command():
    @click.command(help="""
    Add a new delegated target role. Allows optional specification of the role's properties through a JSON configuration file.
    If the configuration file is not provided or specific properties are omitted, default values are used.
    Only a list of one or more delegated paths has to be provided.

    Configuration file (JSON) can specify:
    - 'parent_role' (string): The parent role under which the new role will be delegated. Default is 'targets'.
    - 'delegated_path' (array of strings): Paths to be delegated to the new role. Must specify at least one if using a config file.
    - 'keys_number' (integer): Number of signing keys. Default is 1.
    - 'threshold' (integer): Number of keys required to sign. Default is 1.
    - 'yubikey' (boolean): Whether to use a YubiKey for signing. Default is false.
    - 'scheme' (string): Signature scheme, e.g., 'rsa-pkcs1v15-sha256'. Default is 'rsa-pkcs1v15-sha256'.

    Example JSON structure:
    {
    "parent_role": "targets",
    "delegated_path": ["/delegated_path_inside_targets1", "/delegated_path_inside_targets2"],
    "keys_number": 1,
    "threshold": 1,
    "yubikey": true,
    "scheme": "rsa-pkcs1v15-sha256"
    }
    """)
    @find_repository
    @catch_cli_exception(handle=TAFError)
    @click.argument("role")
    @click.option("--config-file", type=click.Path(exists=True), help="Path to the JSON configuration file.")
    @click.option("--path", default=".", help="Authentication repository's location. If not specified, set to the current directory")
    @click.option("--keystore", default=None, help="Location of the keystore files")
    @click.option("--no-commit", is_flag=True, default=False, help="Indicates that the changes should not be committed automatically")
    @click.option("--prompt-for-keys", is_flag=True, default=False, help="Whether to ask the user to enter their key if not located inside the keystore directory")
    def add(role, config_file, path, keystore, no_commit, prompt_for_keys):

        config_data = {}
        if config_file:
            try:
                config_data = json.loads(Path(config_file).read_text())
            except json.JSONDecodeError:
                click.echo("Invalid JSON provided. Please check your input.", err=True)
                sys.exit(1)

        delegated_path = config_data.get("delegated_path", [])
        if not delegated_path:
            taf_logger.log("NOTICE", "Specify at least one delegated path through a configuration file.")
            return

        parent_role = config_data.get("parent_role", "targets")
        keys_number = config_data.get("keys_number", 1)
        threshold = config_data.get("threshold", 1)
        yubikey = config_data.get("yubikey", False)
        scheme = config_data.get("scheme", DEFAULT_RSA_SIGNATURE_SCHEME)

        add_role(
            path=path,
            role=role,
            parent_role=parent_role,
            paths=delegated_path,
            keys_number=keys_number,
            threshold=threshold,
            yubikey=yubikey,
            keystore=keystore,
            scheme=scheme,
            commit=not no_commit,
            prompt_for_keys=prompt_for_keys,
        )
    return add


def export_roles_description_command():
    @click.command(help="""
        Export roles-description.json file based on the
        """)
    @find_repository
    @catch_cli_exception(handle=TAFError)
    @click.option("--path", default=".", help="Authentication repository's location. If not specified, set to the current directory")
    @click.option("--output", default=None, help="Output file path")
    @click.option("--keystore", default=None, help="Location of the keystore files")
    def export_roles_description(path, output, keystore):
        auth_repo = AuthenticationRepository(path=path)
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


def add_multiple_command():
    @click.command(help="""Adds new roles based on the provided keys-description file by
            comparing it with the current state of the repository.

            The current state can be exported using taf roles export_roles_description and then
            edited manually to add new roles.

            For each role, the following can be defined:
            - Total number of keys per role.
            - Threshold of required signatures per role.
            - Use of Yubikeys or keystore files for storing keys.
            - Signature scheme, with the default being 'rsa-pkcs1v15-sha256'.
            - Keystore path, if not specified via the keystore option.

        \b
        Example of a JSON configuration:
        {
            "roles": {
                "root": {
                    "number": 3,
                    "length": 2048,
                    "passwords": ["password1", "password2", "password3"],
                    "threshold": 2,
                    "yubikey": true
                },
                "targets": {
                    "length": 2048
                },
                "snapshot": {},
                "timestamp": {}
            },
            "keystore": "keystore_path"
        }
        """)
    @find_repository
    @catch_cli_exception(handle=TAFError)
    @click.option("--path", default=".", help="Authentication repository's location. If not specified, set to the current directory")
    @click.argument("keys-description")
    @click.option("--keystore", default=None, help="Location of the keystore files")
    @click.option("--scheme", default=DEFAULT_RSA_SIGNATURE_SCHEME, help="A signature scheme used for signing")
    @click.option("--no-commit", is_flag=True, default=False, help="Indicates that the changes should not be committed automatically")
    @click.option("--prompt-for-keys", is_flag=True, default=False, help="Whether to ask the user to enter their key if not located inside the keystore directory")
    def add_multiple(path, keystore, keys_description, scheme, no_commit, prompt_for_keys):
        add_multiple_roles(
            path=path,
            keystore=keystore,
            roles_key_infos=keys_description,
            scheme=scheme,
            prompt_for_keys=prompt_for_keys,
            commit=not no_commit,
        )
    return add_multiple


def add_role_paths_command():
    @click.command(help="Add a new delegated target role, specifying which paths are delegated to the new role. Its parent role, number of signing keys and signatures threshold can also be defined. Update and sign all metadata files and commit.")
    @find_repository
    @catch_cli_exception(handle=TAFError)
    @click.argument("role")
    @click.option("--path", default=".", help="Authentication repository's location. If not specified, set to the current directory")
    @click.option("--delegated-path", multiple=True, help="Paths associated with the delegated role")
    @click.option("--keystore", default=None, help="Location of the keystore files")
    @click.option("--no-commit", is_flag=True, default=False, help="Indicates that the changes should not be committed automatically")
    @click.option("--prompt-for-keys", is_flag=True, default=False, help="Whether to ask the user to enter their key if not located inside the keystore directory")
    def adding_role_paths(role, path, delegated_path, keystore, no_commit, prompt_for_keys):
        if not delegated_path:
            print("Specify at least one path")
            return

        add_role_paths(
            paths=delegated_path,
            delegated_role=role,
            keystore=keystore,
            commit=not no_commit,
            auth_path=path,
            prompt_for_keys=prompt_for_keys,
            push=not no_commit,
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
    @click.option("--path", default=".", help="Authentication repository's location. If not specified, set to the current directory")
    @click.option("--keystore", default=None, help="Location of the keystore files")
    @click.option("--scheme", default=DEFAULT_RSA_SIGNATURE_SCHEME, help="A signature scheme used for signing")
    @click.option("--remove-targets/--no-remove-targets", default=True, help="Should targets delegated to this role also be removed. If not removed, they are signed by the parent role")
    @click.option("--no-commit", is_flag=True, default=False, help="Indicates that the changes should not be committed automatically")
    @click.option("--prompt-for-keys", is_flag=True, default=False, help="Whether to ask the user to enter their key if not located inside the keystore directory")
    def remove(role, path, keystore, scheme, remove_targets, no_commit, prompt_for_keys):
        remove_role(
            path=path,
            role=role,
            keystore=keystore,
            scheme=scheme,
            remove_targets=remove_targets,
            commit=not no_commit,
            prompt_for_keys=prompt_for_keys,
        )
    return remove


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
    @click.option("--path", default=".", help="Authentication repository's location. If not specified, set to the current directory")
    @click.option("--role", multiple=True, help="A list of roles to whose list of signing keys the new key should be added")
    @click.option("--pub-key-path", default=None, help="Path to the public key corresponding to the private key which should be registered as the role's signing key")
    @click.option("--keystore", default=None, help="Location of the keystore files")
    @click.option("--keys-description", help="A dictionary containing information about the keys or a path to a json file which stores the needed information")
    @click.option("--scheme", default=DEFAULT_RSA_SIGNATURE_SCHEME, help="A signature scheme used for signing")
    @click.option("--no-commit", is_flag=True, default=False, help="Indicates that the changes should not be committed automatically")
    @click.option("--prompt-for-keys", is_flag=True, default=False, help="Whether to ask the user to enter their key if not located inside the keystore directory")
    def adding_signing_key(path, role, pub_key_path, keystore, keys_description, scheme, no_commit, prompt_for_keys):
        if not role:
            print("Specify at least one role")
            return

        add_signing_key(
            path=path,
            roles=role,
            pub_key_path=pub_key_path,
            keystore=keystore,
            roles_key_infos=keys_description,
            scheme=scheme,
            commit=not no_commit,
            prompt_for_keys=prompt_for_keys
        )
    return adding_signing_key


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

    group.add_command(add_role_command(), name='add')
    group.add_command(add_multiple_command(), name='add-multiple')
    group.add_command(add_role_paths_command(), name='add-role-paths')
    # group.add_command(remove_role_command(), name='remove')
    group.add_command(add_signing_key_command(), name='add-signing-key')
    group.add_command(list_keys_command(), name='list-keys')
    group.add_command(export_roles_description_command(), name="export-description")
