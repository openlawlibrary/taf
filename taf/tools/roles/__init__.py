import click
from taf.api.roles import add_role, add_roles, remove_role, add_signing_key as add_roles_signing_key

from taf.constants import DEFAULT_RSA_SIGNATURE_SCHEME


def attach_to_group(group):

    @group.group()
    def roles():
        pass

    @roles.command()
    @click.argument("path")
    @click.argument("role")
    @click.option("--parent-role", default="targets", help="Parent targets role of this role. Defaults to targets")
    @click.option("--delegated-path", multiple=True, help="Paths associated with the delegated role")
    @click.option("--keystore", default=None, help="Location of the keystore files")
    @click.option("--keys-number", default=1, help="Number of signing keys. Defaults to 1")
    @click.option("--threshold", default=1, help="An integer number of keys of that "
                  "role whose signatures are required in order to consider a file as being properly signed by that role")
    @click.option("--yubikey", is_flag=True, default=None, help="A flag determining if the new role should be signed using a Yubikey")
    @click.option("--scheme", default=DEFAULT_RSA_SIGNATURE_SCHEME, help="A signature scheme used for signing")
    def add(path, role, parent_role, delegated_path, keystore, keys_number, threshold, yubikey, scheme):
        """Add a new delegated target role, specifying which paths are delegated to the new role.
        Its parent role, number of signing keys and signatures threshold can also be defined.
        Update and sign all metadata files and commit.
        """
        if not path:
            print("Specify at least one path")
            return

        add_role(path, role, parent_role, delegated_path, keys_number, threshold, yubikey, keystore, scheme)

    @roles.command()
    @click.argument("path")
    @click.argument("keys-description")
    @click.option("--keystore", default=None, help="Location of the keystore files")
    @click.option("--scheme", default=DEFAULT_RSA_SIGNATURE_SCHEME, help="A signature scheme "
                  "used for signing")
    def add_multiple(path, keystore, keys_description, scheme):
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
        add_roles(path, keystore, keys_description, scheme)

    @roles.command()
    @click.argument("path")
    @click.argument("role")
    @click.option("--keystore", default=None, help="Location of the keystore files")
    @click.option("--scheme", default=DEFAULT_RSA_SIGNATURE_SCHEME, help="A signature scheme "
                  "used for signing")
    @click.option("--remove-targets/--no-remove-targets", default=True, help="Should targets delegated to this "
                  "role also be removed. If not removed, they are signed by the parent role")
    def remove(path, role, keystore, scheme, remove_targets):
        """Remove a delegated target role, and, optionally, its targets (depending on the remove-targets parameter).
        If targets should also be deleted, target files are remove and their corresponding entires are removed
        from repositoires.json. If targets should not get removed, the target files are signed using the
        removed role's parent role
        """
        remove_role(path, role, keystore, scheme=scheme, remove_targets=remove_targets, commit=True)

    @roles.command()
    @click.argument("path")
    @click.option("--role", multiple=True, help="A list of roles to whose list of signing keys "
                  "the new key should be added")
    @click.option("--pub-key-path", default=None, help="Path to the public key corresponding to "
                  "the private key which should be registered as the role's signing key")
    @click.option("--keystore", default=None, help="Location of the keystore files")
    @click.option("--keys-description", help="A dictionary containing information about the "
                  "keys or a path to a json file which stores the needed information")
    @click.option("--scheme", default=DEFAULT_RSA_SIGNATURE_SCHEME, help="A signature scheme "
                  "used for signing")
    def add_signing_key(path, role, pub_key_path, keystore, keys_description, scheme):
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
        add_roles_signing_key(path, role, pub_key_path, keystore,
                              keys_description, scheme)
