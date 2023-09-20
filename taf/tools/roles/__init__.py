import click
from taf.api.roles import add_role, add_roles, list_keys_of_role, remove_role, add_signing_key as add_roles_signing_key
from taf.constants import DEFAULT_RSA_SIGNATURE_SCHEME
from taf.exceptions import TAFError
from taf.tools.cli import catch_cli_exception


def attach_to_group(group):

    @group.group()
    def roles():
        pass

    @roles.command()
    @catch_cli_exception(handle=TAFError)
    @click.argument("role")
    @click.option("--path", default=".", help="Authentication repository's location. If not specified, set to the current directory")
    @click.option("--parent-role", default="targets", help="Parent targets role of this role. Defaults to targets")
    @click.option("--delegated-path", multiple=True, help="Paths associated with the delegated role")
    @click.option("--keystore", default=None, help="Location of the keystore files")
    @click.option("--keys-number", default=1, help="Number of signing keys. Defaults to 1")
    @click.option("--threshold", default=1, help="An integer number of keys of that "
                  "role whose signatures are required in order to consider a file as being properly signed by that role")
    @click.option("--yubikey", is_flag=True, default=None, help="A flag determining if the new role should be signed using a Yubikey")
    @click.option("--scheme", default=DEFAULT_RSA_SIGNATURE_SCHEME, help="A signature scheme used for signing")
    @click.option("--no-commit", is_flag=True, default=False, help="Indicates that the changes should not be "
                  "committed automatically")
    @click.option("--prompt-for-keys", is_flag=True, default=False, help="Whether to ask the user to enter their key if not "
                  "located inside the keystore directory")
    def add(role, path, parent_role, delegated_path, keystore, keys_number, threshold, yubikey, scheme, no_commit, prompt_for_keys):
        """Add a new delegated target role, specifying which paths are delegated to the new role.
        Its parent role, number of signing keys and signatures threshold can also be defined.
        Update and sign all metadata files and commit.
        """
        if not path:
            print("Specify at least one path")
            return

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

    @roles.command()
    @catch_cli_exception(handle=TAFError)
    @click.option("--path", default=".", help="Authentication repository's location. If not specified, set to the current directory")
    @click.argument("keys-description")
    @click.option("--keystore", default=None, help="Location of the keystore files")
    @click.option("--scheme", default=DEFAULT_RSA_SIGNATURE_SCHEME, help="A signature scheme "
                  "used for signing")
    @click.option("--no-commit", is_flag=True, default=False, help="Indicates that the changes should not be "
                  "committed automatically")
    @click.option("--prompt-for-keys", is_flag=True, default=False, help="Whether to ask the user to enter their key if not "
                  "located inside the keystore directory")
    def add_multiple(path, keystore, keys_description, scheme, no_commit, prompt_for_keys):
        """Add one or more target roles. Information about the roles
        can be provided through a dictionary - either specified directly or contained
        by a .json file whose path is specified when calling this command. This allows
        definition of:
            - total number of keys per role
            - threshold of signatures per role
            - should keys of a role be on Yubikeys or should keystore files be used
            - scheme (the default scheme is rsa-pkcs1v15-sha256)
            - keystore path, if not specified via keystore option

        \b
        For example:
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
        """
        add_roles(
            path=path,
            keystore=keystore,
            roles_key_infos=keys_description,
            scheme=scheme,
            prompt_for_keys=prompt_for_keys,
            commit=not no_commit,
        )

    @roles.command()
    @catch_cli_exception(handle=TAFError)
    @click.argument("role")
    @click.option("--path", default=".", help="Authentication repository's location. If not specified, set to the current directory")
    @click.option("--keystore", default=None, help="Location of the keystore files")
    @click.option("--scheme", default=DEFAULT_RSA_SIGNATURE_SCHEME, help="A signature scheme "
                  "used for signing")
    @click.option("--remove-targets/--no-remove-targets", default=True, help="Should targets delegated to this "
                  "role also be removed. If not removed, they are signed by the parent role")
    @click.option("--no-commit", is_flag=True, default=False, help="Indicates that the changes should not be "
                  "committed automatically")
    @click.option("--prompt-for-keys", is_flag=True, default=False, help="Whether to ask the user to enter their key if not "
                  "located inside the keystore directory",)
    def remove(role, path, keystore, scheme, remove_targets, no_commit, prompt_for_keys):
        """Remove a delegated target role, and, optionally, its targets (depending on the remove-targets parameter).
        If targets should also be deleted, target files are remove and their corresponding entires are removed
        from repositoires.json. If targets should not get removed, the target files are signed using the
        removed role's parent role
        """
        remove_role(
            path=path,
            role=role,
            keystore=keystore,
            scheme=scheme,
            remove_targets=remove_targets,
            commit=not no_commit,
            prompt_for_keys=prompt_for_keys,
        )

    @roles.command()
    @catch_cli_exception(handle=TAFError)
    @click.option("--path", default=".", help="Authentication repository's location. If not specified, set to the current directory")
    @click.option("--role", multiple=True, help="A list of roles to whose list of signing keys "
                  "the new key should be added")
    @click.option("--pub-key-path", default=None, help="Path to the public key corresponding to "
                  "the private key which should be registered as the role's signing key")
    @click.option("--keystore", default=None, help="Location of the keystore files")
    @click.option("--keys-description", help="A dictionary containing information about the "
                  "keys or a path to a json file which stores the needed information")
    @click.option("--scheme", default=DEFAULT_RSA_SIGNATURE_SCHEME, help="A signature scheme "
                  "used for signing")
    @click.option("--no-commit", is_flag=True, default=False, help="Indicates that the changes should not be "
                  "committed automatically")
    @click.option("--prompt-for-keys", is_flag=True, default=False, help="Whether to ask the user to enter their key if not "
                  "located inside the keystore directory")
    def add_signing_key(path, role, pub_key_path, keystore, keys_description, scheme, no_commit, prompt_for_keys):
        """
        Add a new signing key. This will make it possible to a sign metadata files
        corresponding to the specified roles with another key. Although private keys are
        used for signing, key identifiers are calculated based on the public keys. This
        means that it's necessary to enter the public key in order to register
        a new signing key. Public key can be loaded from a file, in which case it is
        necessary to specify its path as the pub_key parameter's value. If this option
        is not used when calling this command, the key can be directly entered later.
        """
        if not len(role):
            print("Specify at least one role")
            return
        add_roles_signing_key(
            path=path,
            roles=role,
            pub_key_path=pub_key_path,
            keystore=keystore,
            roles_key_infos=keys_description,
            scheme=scheme,
            commit=not no_commit,
            prompt_for_keys=prompt_for_keys
        )

    @roles.command()
    @catch_cli_exception(handle=TAFError)
    @click.argument("role")
    @click.option("--path", default=".", help="Authentication repository's location. If not specified, set to the current directory")
    def list_keys(role, path):
        """
        List all keys of the specified role. If certs directory exists and contains certificates exported from YubiKeys,
        include additional information read from these certificates, like name or organization.
        """
        list_keys_of_role(
            path=path,
            role=role,
        )
