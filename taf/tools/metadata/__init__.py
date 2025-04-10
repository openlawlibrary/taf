import click
from pathlib import Path
from taf.api.metadata import update_metadata_expiration_date, check_expiration_dates, add_key_names
from taf.constants import DEFAULT_RSA_SIGNATURE_SCHEME
from taf.exceptions import TAFError
from taf.tools.cli import catch_cli_exception, common_repo_edit_options, find_repository
from taf.tools.repo import pin_managed
from taf.utils import ISO_DATE_PARAM_TYPE as ISO_DATE
from taf.log import taf_logger
import datetime


def add_key_names_command():
    @click.command(help="""If key names are not specified when creating repositories or adding a new role, "
        "this command can be used to specify names of keys given a name-public key mapping.""")
    @find_repository
    @common_repo_edit_options
    @click.option("--path", default=".", help="Authentication repository's location. If not specified, set to the current directory")
    @click.option("--commit-msg", default=None, help="Commit message")
    @pin_managed
    def adding_key_names(path, keys_description, keystore, pin_manager, no_commit, no_remote_check, prompt_for_keys, commit_msg):
        if not keys_description or Path(keys_description).is_file():
            taf_logger.error("Provide a path to an existing keys-description file")

        add_key_names(
            path=path,
            keys_description=Path(keys_description),
            keystore=keystore, pin_manager=pin_manager,
            commit=not no_commit,
            skip_remote_check=no_remote_check,
            prompt_for_keys=prompt_for_keys,
            commit_msg=commit_msg,
        )
    return adding_key_names


def check_expiration_dates_command():
    @click.command(help="""Check if the expiration dates of the metadata roles is still within an interval threshold.
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
            root will expire on 2022-08-19""")
    @find_repository
    @click.option("--path", default=".", help="Authentication repository's location. If not specified, set to the current directory")
    @click.option("--interval", default=30, type=int, help="Number of days added to the start date")
    @click.option("--start-date", default=datetime.datetime.now(), help="Date to which expiration interval is added", type=ISO_DATE)
    def checking_expiration_dates(path, interval, start_date):
        check_expiration_dates(path=path, interval=interval, start_date=start_date)
    return checking_expiration_dates


def update_expiration_dates_command():
    @click.command(help="""Update expiration date of the metadata file corresponding to the specified role.
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

        If targets or other delegated role is updated, automatically sign snapshot and timestamp.""")
    @find_repository
    @catch_cli_exception(handle=TAFError)
    @common_repo_edit_options
    @click.option("--path", default=".", help="Authentication repository's location. If not specified, set to the current directory")
    @click.option("--role", multiple=True, help="A list of roles which expiration date should get updated")
    @click.option("--interval", default=None, type=int, help="Number of days added to the start date")
    @click.option("--scheme", default=DEFAULT_RSA_SIGNATURE_SCHEME, help="A signature scheme used for signing")
    @click.option("--start-date", default=datetime.datetime.now(), type=ISO_DATE, help="Date to which the interval is added")
    @click.option("--commit-msg", default=None, help="Commit message")
    @pin_managed
    def update_expiration_dates(path, role, interval, keystore, scheme, start_date, no_commit, prompt_for_keys, pin_manager, keys_description, no_remote_check, commit_msg):
        if not len(role):
            print("Specify at least one role")
            return
        update_metadata_expiration_date(
            path=path,
            pin_manager=pin_manager,
            roles=role,
            interval=interval,
            keystore=keystore,
            scheme=scheme,
            start_date=start_date,
            commit=not no_commit,
            prompt_for_keys=prompt_for_keys,
            keys_description=keys_description,
            skip_remote_check=no_remote_check,
            commit_msg=commit_msg,
        )
    return update_expiration_dates


def attach_to_group(group):
    group.add_command(add_key_names_command(), name="add-key-names")
    group.add_command(check_expiration_dates_command(), name='check-expiration-dates')
    group.add_command(update_expiration_dates_command(), name='update-expiration-dates')
