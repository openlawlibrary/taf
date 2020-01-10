import click
import taf.developer_tool as developer_tool


def attach_to_group(group):

    @group.group()
    def repo():
        pass

    @repo.command()
    @click.argument("path")
    @click.option("--keys-description', help='A dictionary containing information about the "
                  "keys or a path to a json file which which stores the needed information")
    @click.option("--keystore", default=None, help='Location of the keystore files')
    @click.option("--commit-msg", default=None, help='Commit message. If provided, the "
                  "changes will be committed automatically")
    @click.option("--test", is_flag=True, default=False, help='Indicates if the created repository '
                  'is a test authentication repository')
    def create(path, keys_description, keystore, commit_msg, test):
        """
        Create a new authentication repository at the specified location by registering
        signing keys and generating initial metadata files. Information about the roles
        can be provided through a dictionary - either specified directly or contained
        by a .json file whose path is specified when calling this command. This allows
        definition of:
            - total number of keys per role
            - threshold of signatures per role
            - should keys of a role be on Yubikeys or should keystore files be used

        If this dictionary is not specified, it will be assumed that there should only
        be one signing key and that all keys are stored in keystore files.

        For example:\n
        {\n
            "root": {\n
                "number": 3,\n
                "length": 2048,\n
                "passwords": ["password1", "password2", "password3"]\n
                "threshold": 2,\n
                "yubikey": true\n
            },\n
            "targets": {\n
                "length": 2048\n
            },\n
            "snapshot": {},\n
            "timestamp": {}\n
            }\n

        If keys should be stored in keystore files, it is possible to either use already generated
        keys (stored in keystore files located at the path specified using the keystore option),
        or to generate new one.

        If the test flag is set, a special target file will be created. This means that when
        calling the updater, it'll be necessary to use the --authenticate-test-repo flag.
        """
        developer_tool.create_repository(path, keystore, keys_description, commit_msg, test)
