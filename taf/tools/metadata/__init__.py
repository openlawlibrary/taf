import click
import taf.developer_tool as developer_tool
from taf.constants import DEFAULT_RSA_SIGNATURE_SCHEME
from taf.utils import ISO_DATE_PARAM_TYPE as ISO_DATE
import datetime


def attach_to_group(group):

    @group.group()
    def metadata():
        pass

    @metadata.command()
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
        developer_tool.add_signing_key(path, role, pub_key_path, keystore,
                                       keys_description, scheme)

    @metadata.command()
    @click.argument("path")
    @click.argument("keys-description")
    @click.option("--keystore", default=None, help="Location of the keystore files")
    @click.option("--scheme", default=DEFAULT_RSA_SIGNATURE_SCHEME, help="A signature scheme "
                  "used for signing")
    def add_roles(path, keystore, keys_description, scheme):
        developer_tool.add_roles(path, keystore, keys_description, scheme)

    @metadata.command()
    @click.argument("path")
    @click.option("--interval", default=30, type=int, help="Number of days added to the start date")
    @click.option("--start-date", default=datetime.datetime.now(), help="Date to which expiration interval is added", type=ISO_DATE)
    def check_expiration_dates(path, interval, start_date):
        """
        Check if the expiration dates of the metadata roles is still within an interval threshold.
        Expiration date is calculated by adding interval to start date. Interval is specified in days.
        The default value for interval in method is set to 30 days.
        Result contains metadata roles which have already expired and also roles which will expire (within the interval).
        Result is printed to the console and contains the following information:
        header:
            - start date
            - interval (in days)
        information:
            - role name
            - expiration date
        Example console output:
        Given a 30 day interval from today (2022-07-22):
            timestamp will expire on 2022-07-22
            snapshot will expire on 2022-07-28
            root will expire on 2022-08-19
        """
        developer_tool.check_expiration_dates(repo_path=path, interval=interval, start_date=start_date)

    @metadata.command()
    @click.argument("path")
    @click.option("--role", multiple=True, help="A list of roles which expiration date should get updated")
    @click.option("--interval", default=None, help="Number of days added to the start date",
                  type=int)
    @click.option("--keystore", default=None, help="Location of the keystore files")
    @click.option("--scheme", default=DEFAULT_RSA_SIGNATURE_SCHEME, help="A signature scheme "
                  "used for signing")
    @click.option("--start-date", default=datetime.datetime.now(), help="Date to which the "
                  "interval is added", type=ISO_DATE)
    @click.option("--no-commit", is_flag=True, default=False, help="Indicates if the changes should not be "
                  "committed automatically")
    def update_expiration_date(path, role, interval, keystore, scheme, start_date, no_commit):
        """
        \b
        Update expiration date of the metadata file corresponding to the specified role.
        The new expiration date is calculated by adding interval to start date. The default
        value of the start date parameter is the current date, while default interval depends
        on the role and is:
            - 365 in case of root
            - 90  in case of targets
            - 7 in case of snapshot
            - 1 in case of timestamp and all other roles
        The updated metadata file is then signed. If the signing key should be loaded from
        the keystore file, it's necessary to specify its path when calling this command. If
        that is not the case, it will be needed to either enter the signing key directly or
        sign the file using a yubikey.

        If targets or other delegated role is updated, automatically sign snapshot and timestamp.
        """
        if not len(role):
            print("Specify at least one role")
            return
        developer_tool.update_metadata_expiration_date(path, role, interval, keystore,
                                                       scheme, start_date, no_commit)
