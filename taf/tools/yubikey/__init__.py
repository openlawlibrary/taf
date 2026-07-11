import click
from taf.api.yubikey import (
    SETUP_SLOTS,
    export_yk_certificate,
    export_yk_public_pem,
    get_yk_roles,
    list_yk_slots,
    setup_signing_yubikey,
    setup_test_yubikey,
)
from taf.exceptions import YubikeyError
from taf.repository_utils import find_valid_repository
from taf.tools.cli import catch_cli_exception
from taf.tools.repo import pin_managed
from taf.yubikey.yubikey import list_connected_yubikeys, list_all_devices

SETUP_SLOT_NAMES = [s.name for s in SETUP_SLOTS]


def check_pin_command():
    @click.command(help="Checks if the specified pin is valid")
    @click.option("--pin", default=None, help="PIN to be checked")
    @click.option(
        "--serial",
        default=None,
        type=int,
        help="Serial number of a YubiKey. Has to be provided if more than one YK is inserted",
    )
    @catch_cli_exception(handle=YubikeyError)
    def check_pin(pin, serial):
        try:
            from taf.yubikey.yubikey import is_valid_pin, get_and_validate_pin

            if serial is None and len(list_all_devices()) > 1:
                click.echo(
                    "More than one YubiKey is inserted. Please specify the serial number of the YubiKey to be used"
                )
                return
            name = serial or "YubiKey"
            if pin is None:
                get_and_validate_pin(name, serial=serial)
            else:
                is_valid, retries = is_valid_pin(pin, serial=serial)
                if not is_valid:
                    click.echo(f"Invalid PIN. You have {retries} retries left")
        except Exception as e:
            click.echo(f"Error: {e}")
            return

    return check_pin


def export_pub_key_command():
    @click.command(help="Export public keys of the inserted YubiKeys")
    @click.option(
        "--output",
        help="File to which the exported public key will be written. The result will be written to the console if path is not specified",
    )
    @catch_cli_exception(handle=YubikeyError)
    def export_pub_key(output):
        export_yk_public_pem(output)

    return export_pub_key


def get_roles_command():
    @click.command(help="List roles the inserted YubiKey is allowed to sign.")
    @catch_cli_exception(handle=YubikeyError, print_error=True)
    @click.option(
        "--path",
        default=".",
        help="Authentication repository's location. If not specified, set to the current directory",
    )
    @catch_cli_exception(handle=YubikeyError)
    def get_roles(path):
        path = find_valid_repository(path)
        roles_with_paths = get_yk_roles(path)
        for serial, roles_and_paths in roles_with_paths.items():
            print(f"\nSerial: {serial}")
            for role, paths in roles_and_paths.items():
                print(f"\n{role}")
                for path in paths:
                    print(f"\n -{path}")

    return get_roles


def export_certificate_command():
    @click.command(help="Export certificates of the inserted YubiKeys")
    @click.option(
        "--output",
        help="File to which the exported certificate key will be written. The result will be written to the user's home directory by default",
    )
    @catch_cli_exception(handle=YubikeyError)
    def export_certificate(output):
        export_yk_certificate(output)

    return export_certificate


def list_key_command():
    @click.command(help="List All Connected Keys and their information")
    @catch_cli_exception(handle=YubikeyError)
    def list_keys():
        list_connected_yubikeys()

    return list_keys


def setup_signing_key_command():
    @click.command(
        help="""Generate a new key on the yubikey and copy it to the given PIV slot.
        Export the generated certificate to the specified directory.
        WARNING - --reset will factory-reset the card, deleting everything on it first."""
    )
    @click.option(
        "--certs-dir",
        help="Path of the directory where the exported certificate will be saved. Set to the user home directory by default",
    )
    @click.option(
        "--slot",
        type=click.Choice(SETUP_SLOT_NAMES),
        default="SIGNATURE",
        help="PIV slot to set the key up in. Defaults to SIGNATURE.",
    )
    @click.option(
        "--force",
        is_flag=True,
        default=False,
        help="Overwrite the target slot if it's already occupied. Has no effect if "
        "resetting, since that always leaves every slot empty regardless",
    )
    @click.option(
        "--reset/--no-reset",
        default=False,
        help="Whether to factory-reset the card first. Defaults to False.",
    )
    @catch_cli_exception(handle=YubikeyError)
    @pin_managed
    def setup_signing_key(certs_dir, slot, force, reset, pin_manager):
        setup_signing_yubikey(
            pin_manager, certs_dir, key_size=2048, slot=slot, force=force, reset=reset
        )

    return setup_signing_key


def list_slots_command():
    @click.command(
        help="Show which PIV slots on the inserted YubiKey(s) are free and which are occupied."
    )
    @click.option(
        "--serial",
        default=None,
        help="Serial number of a specific YubiKey. Lists slots for every inserted YubiKey if not specified",
    )
    @catch_cli_exception(handle=YubikeyError)
    def list_slots(serial):
        list_yk_slots(serial)

    return list_slots


def setup_test_key_command():
    @click.command(
        help="""Copies the specified key onto the given PIV slot of the inserted YubiKey.
        WARNING - --reset will factory-reset the card, deleting everything on it first."""
    )
    @click.argument("key-path")
    @click.option(
        "--slot",
        type=click.Choice(SETUP_SLOT_NAMES),
        default="SIGNATURE",
        help="PIV slot to copy the key into. Defaults to SIGNATURE.",
    )
    @click.option(
        "--force",
        is_flag=True,
        default=False,
        help="Overwrite the target slot if it's already occupied. Has no effect if "
        "resetting, since that always leaves every slot empty regardless",
    )
    @click.option(
        "--reset/--no-reset",
        default=False,
        help="Whether to factory-reset the card first. Defaults to False.",
    )
    @catch_cli_exception(handle=YubikeyError)
    @pin_managed
    def setup_test_key(key_path, slot, force, reset, pin_manager):
        setup_test_yubikey(pin_manager, key_path, slot=slot, force=force, reset=reset)

    return setup_test_key


def attach_to_group(group):
    group.add_command(check_pin_command(), name="check-pin")
    group.add_command(export_pub_key_command(), name="export-pub-key")
    group.add_command(get_roles_command(), name="get-roles")
    group.add_command(export_certificate_command(), name="export-certificate")
    group.add_command(list_key_command(), name="list-key")
    group.add_command(setup_signing_key_command(), name="setup-signing-key")
    group.add_command(setup_test_key_command(), name="setup-test-key")
    group.add_command(list_slots_command(), name="list-slots")
