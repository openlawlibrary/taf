import click
import json
from taf.api.roles import add_role, remove_role

from taf.constants import DEFAULT_RSA_SIGNATURE_SCHEME

def attach_to_group(group):

    @group.group()
    def roles():
        pass



    @roles.command()
    @click.argument("auth-path")
    @click.argument("role")
    @click.option("--parent-role", default="targets", help="Parent targets role of this role. Defaults to targets")
    @click.option("--path", multiple=True, help="Paths associated with the delegated role")
    @click.option("--keystore", default=None, help="Location of the keystore files")
    @click.option("--keys-number", default=1, help="Number of signing keys. Defaults to 1")
    @click.option("--threshold", default=1, help="An integer number of keys of that "
                    "role whose signatures are required in order to consider a file as being properly signed by that role")
    @click.option("--yubikey", is_flag=True, default=None, help="A flag determining if the new role should be signed using a Yubikey")
    @click.option("--scheme", default=DEFAULT_RSA_SIGNATURE_SCHEME, help="A signature scheme used for signing")
    def add(auth_path, role, parent_role, path, keystore, keys_number, threshold, yubikey, scheme):
        """Add a new delegated target role, specifying which paths are delegated to the new role.
        Its parent role, number of signing keys and signatures threshold can also be defined.
        Update and sign all metadata files and commit.
        """
        if not path:
            print("Specify at least one path")
            return

        add_role(auth_path, role, parent_role, path, keys_number, threshold, yubikey, keystore, scheme)


    @roles.command()
    @click.argument("auth-path")
    @click.argument("role")
    @click.option("--keystore", default=None, help="Location of the keystore files")
    @click.option("--scheme", default=DEFAULT_RSA_SIGNATURE_SCHEME, help="A signature scheme "
                    "used for signing")
    @click.option("--remove-targets/--no-remove-targets", default=True, help="Should targets delegated to this "
                   "role also be removed. If not removed, they are signed by the parent role")
    def remove(auth_path, role, keystore, scheme, remove_targets):
        """Remove a delegated target role, and, optionally, its targets (depending on the remove-targets parameter).
        If targets should also be deleted, target files are remove and their corresponding entires are removed
        from repositoires.json. If targets should not get removed, the target files are signed using the
        removed role's parent role
        """
        remove_role(auth_path, role, keystore, scheme=scheme, remove_targets=remove_targets, commit=True)
