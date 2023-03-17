import click
import json
from taf.api.roles import add_role

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
        """Export lists of sorted commits, grouped by branches and target repositories, based
        on target files stored in the authentication repository. If commit is specified,
        only return changes made at that revision and all subsequent revisions. If it is not,
        start from the initial authentication repository commit.
        Repositories which will be taken into consideration when collecting targets historical
        data can be defined using the repo option. If no repositories are passed in, historical
        data will include all target repositories.
        to a file whose location is specified using the output option, or print it to
        console.
        """
        if path is None:
            print("Specify at least one path")
            return

        add_role(auth_path, role, parent_role, path, keys_number, threshold, yubikey, keystore, scheme)
