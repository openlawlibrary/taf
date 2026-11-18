import click
from taf.api.keystore import generate_keys
from taf.exceptions import KeystoreError
from taf.tools.cli import catch_cli_exception


def generate_keys_command():
    @click.command(
        help="""Generate keystore files and save them to the specified location given a dictionary containing
        information about each role - total number of keys, their signing scheme, thresholds and,
        for RSA keys, their lengths. The scheme sets the type of the generated keys and has to be specified.
        It is necessary to either directly specify this dictionary when calling this command or
        to provide a path to a `.json` file which contains the needed information.

        \b
        Keys description example:
        {
            "roles": {
                "root": {
                    "number": 3,
                    "threshold": 2,
                    "scheme": "ecdsa-sha2-nistp384"
                },
                "targets": {
                    "scheme": "ed25519"
                },
                "snapshot": {
                    "scheme": "rsa-pkcs1v15-sha256",
                    "length": 2048
                },
                "timestamp": {
                    "scheme": "ecdsa-sha2-nistp256"
                }
            },
            "keystore": "keystore_path"
        }

        Default number of keys and threshold are 1 and length of RSA keys is 3072.
        If keystore location is specified through the keystore input parameter and not listed
        in keys-description dictionary, keys will be saved to ./keystore"""
    )
    @catch_cli_exception(handle=KeystoreError, print_error=True)
    @click.option(
        "--keystore",
        default=None,
        help="Location of the keystore directory. Can be specified in keys-description dictionary",
    )
    @click.option(
        "--keys-description",
        help="A dictionary containing information about the keys or a path to a json file which stores the needed information",
    )
    def generate(keystore, keys_description):
        generate_keys(keystore, keys_description)

    return generate


def attach_to_group(group):
    group.add_command(generate_keys_command(), name="generate")


@click.group()
def cli():
    pass


attach_to_group(cli)

if __name__ == "__main__":
    cli()
