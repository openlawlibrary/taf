import click
import json
from taf.api.yubikey import export_yk_certificate, export_yk_public_pem, get_yk_roles, setup_signing_yubikey, setup_test_yubikey
from taf.exceptions import YubikeyError
from taf.repository_utils import find_valid_repository
from taf.tools.cli import catch_cli_exception


def check_pin_command():
    @click.command(help="Checks if the specified pin is valid")
    @click.argument("pin")
    def check_pin(pin):
        try:
            from taf.yubikey import is_valid_pin
            valid, retries = is_valid_pin(pin)
            inserted = True
        except YubikeyError:
            valid = False
            inserted = False
            retries = None
        print(json.dumps({
            "pin": valid,
            "retries": retries,
            "inserted": inserted
        }))
    return check_pin


def export_pub_key_command():
    @click.command(help="Export the inserted Yubikey's public key and save it to the specified location.")
    @click.option("--output", help="File to which the exported public key will be written. The result will be written to the console if path is not specified")
    def export_pub_key(output):
        export_yk_public_pem(output)
    return export_pub_key


def get_roles_command():
    @click.command(help="Export the inserted Yubikey's public key and save it to the specified location.")
    @catch_cli_exception(handle=YubikeyError, print_error=True)
    @click.option("--path", default=".", help="Authentication repository's location. If not specified, set to the current directory")
    def get_roles(path):
        path = find_valid_repository(path)
        roles_with_paths = get_yk_roles(path)
        for role, paths in roles_with_paths.items():
            print(f"\n{role}")
            for path in paths:
                print(f"\n -{path}")
    return get_roles


def export_certificate_command():
    @click.command(help="Export the inserted Yubikey's public key and save it to the specified location.")
    @click.option("--output", help="File to which the exported certificate key will be written. The result will be written to the user's home directory by default")
    def export_certificate(output):
        export_yk_certificate(output)
    return export_certificate


def setup_signing_key_command():
    @click.command(help="""Generate a new key on the yubikey and set the pin. Export the generated certificate
        to the specified directory.
        WARNING - this will delete everything from the inserted key.""")
    @click.option("--certs-dir", help="Path of the directory where the exported certificate will be saved. Set to the user home directory by default")
    def setup_signing_key(certs_dir):
        setup_signing_yubikey(certs_dir,key_size=2048)
    return setup_signing_key


def setup_test_key_command():
    @click.command(help="""Copies the specified key onto the inserted YubiKey
        WARNING - this will reset the inserted key.""")
    @click.argument("key-path")
    def setup_test_key(key_path):
        setup_test_yubikey(key_path,key_size=2048)
    return setup_test_key


def attach_to_group(group):
    group.add_command(check_pin_command(), name='check-pin')
    group.add_command(export_pub_key_command(), name='export-pub-key')
    group.add_command(get_roles_command(), name='get-roles')
    group.add_command(export_certificate_command(), name='export-certificate')
    group.add_command(setup_signing_key_command(), name='setup-signing-key')
    group.add_command(setup_test_key_command(), name='setup-test-key')
