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
    @click.argument("role", help="Metadata role whose expiration date should be updated")
    @click.option("--interval", default=None, help="Number of days added to the start date",
                  type=int)
    @click.option("--keystore", default=None, help="Location of the keystore files")
    @click.option("--scheme", default=DEFAULT_RSA_SIGNATURE_SCHEME, help="A signature scheme "
                  "used for signing")
    @click.option("--start-date", default=datetime.datetime.now(), help="Date to which the "
                  "interval is added", type=ISO_DATE)
    @click.option("--commit", is_flag=True, help="Indicates if the changes should be "
                  "committed automatically")
    def update_expiration_date(path, role, interval, keystore, scheme, start_date, commit):
        """
        Update expiration date of the metadata file corresponding to the specified role.
        The new expiration date is calculated by adding interval to start date. The default
        value of the start date parameter is the current date, while default interval depends
        on the role and is:
            - 365 in case of root
            - 90  in case of targets
            - 7 in case of shapshot
            - 1 in case of timestamp and all other roles
        The updated metadata file is then signed. If the signing key should be loaded from
        the keystore file, it's necessary to specify its path when calling this command. If
        it is not specified, it will be needed to either enter the signing key directly or
        sign the file using a yubikey.
        """
        developer_tool.update_metadata_expiration_date(path, role, interval, keystore,
                                                       scheme, start_date, commit)
