import click
import json
from taf.api.roles import add_role, remove_role

from taf.constants import DEFAULT_RSA_SIGNATURE_SCHEME

def attach_to_group(group):

    @group.group()
    def roles():
        pass


# parent_role: str, threshold: int, yubikey: bool, keystore: str, scheme: str

    @roles.command()
    @click.argument("auth-path")
    @click.argument("role")
    @click.option("--parent-role", default="targets", help="Parent targets role of this role. Defaults to targets")
    @click.option("--path", multiple=True, help="Paths associated with the delegated role")
    @click.option("--keystore", default=None, help="Location of the keystore files")
    @click.option("--keys-number", default=1, help="Number of signing keys. Defaults to 1")
    @click.option("--threshold", default=1, help="An integer number of keys of that "
                    "role whose signatures are required in order to consider a file as being properly signed by that role")
    @click.option("--yubikey", is_flag=True, default=None, help="Location of the keystore files")
    @click.option("--scheme", default=DEFAULT_RSA_SIGNATURE_SCHEME, help="A signature scheme "
                    "used for signing")
    def add(auth_path, role, parent_role, path, keystore, keys_number, threshold, yubikey, scheme):
        """Add a new delegated target role
        """
        if path is None:
            print("Specify at least one path")
            return

        add_role(auth_path, role, parent_role, path, keys_number, threshold, yubikey, keystore, scheme)


    @roles.command()
    @click.argument("auth-path")
    @click.argument("role")
    @click.option("--keystore", default=None, help="Location of the keystore files")
    @click.option("--scheme", default=DEFAULT_RSA_SIGNATURE_SCHEME, help="A signature scheme "
                    "used for signing")
    def remove(auth_path, role, keystore, scheme):
        """Remove a delegated target role
        """
        remove_role(auth_path, role, keystore, scheme)
