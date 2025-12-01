import click
from taf.api.conf import init


def init_command():
    @click.command(help="Create a .taf directory")
    @click.option(
        "--path",
        default=".",
        help=".taf directory's location. If not specified, set to the current directory",
    )
    @click.option(
        "--keystore",
        default=None,
        help="Location of the keystore directory to copy from. Can be specified in keys-description dictionary",
    )
    @click.option(
        "--keys-description",
        help="A dictionary containing information about the keys or a path to a json file which stores the needed information",
    )
    @click.option(
        "--skip-keygen",
        is_flag=True,
        default=False,
        help="Skip generation of keys even if they do not exist",
    )
    def _init_command(path, keystore, keys_description, skip_keygen):
        init(path, keystore, keys_description, skip_keygen)

    return _init_command


def attach_to_group(group):
    group.add_command(init_command(), name="init")
