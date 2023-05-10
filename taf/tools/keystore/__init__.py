import click
from taf.api.keystore import generate_keys


def attach_to_group(group):
    @group.group()
    def keystore():
        pass

    @keystore.command()
    @click.option("--keystore", default=None, help="Location of the keystore directory. Can be specified in "
                  "keys-description dictionary")
    @click.option("--keys-description", help="A dictionary containing information about the "
                  "keys or a path to a json file which stores the needed information")
    def generate(keystore, keys_description):
        """Generate keystore files and save them to the specified location given a dictionary containing
        information about each role - total number of keys, their lengths and keystore files' passwords.
        It is necessary to either directly specify this dictionary when calling this command or
        to provide a path to a `.json` file which contains the needed information.

        \b
        Keys description example:
        {
            "roles": {
                "root": {
                    "number": 3,
                    "length": 2048,
                    "passwords": ["password1", "password2", "password3"],
                    "threshold": 2
                },
                "targets": {
                    "length": 2048
                },
                "snapshot": {},
                "timestamp": {}
            },
            "keystore: keystore-location
        }

        Default number of keys and threshold are 1, length 3072 and password is an empty string.
        If keystore location is specified through the keystore input parameter and not listed
        in keys-description dictionary, keys will be saved to ./keystore
        """
        generate_keys(keystore, keys_description)
