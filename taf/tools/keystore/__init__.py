import click
import taf.developer_tool as developer_tool


def attach_to_group(group):
    @group.group()
    def keystore():
        pass

    @keystore.command()
    @click.argument("path")
    @click.argument("keys-description")
    def generate(path, keys_description):
        """Generate keystore files and save them to the specified location given a dictionary containing
        information about each role - total number of keys, their lengths and keystore files' passwords.
        It is necessary to either directly specify this dictionary when calling this command or
        to provide a path to a `.json` file which contains the needed information.

        \b
        Keys description example:
        {
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
        }

        Default number of keys and threshold are 1, length 3072 and password is an empty string.
        """
        developer_tool.generate_keys(path, keys_description)
