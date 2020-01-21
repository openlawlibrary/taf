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

        Keys description example: \n
        {\n
            "root": {\n
                "number": 3,\n
                "length": 2048,\n
                "passwords": ["password1", "password2", "password3"]\n
                "threshold": 2,\n
            },\n
            "targets": {\n
                "length": 2048\n
            },\n
            "snapshot": {},\n
            "timestamp": {}\n
            }\n

        Default number of keys and threshold are 1, length 3072 and password is an emtpy string
        """
        developer_tool.generate_keys(path, keys_description)
