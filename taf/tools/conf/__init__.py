import click
from taf.api.conf import init


def init_command():
    @click.option("--path", default=".", help=".taf directory's location. If not specified, set to the current directory")
    @click.option("--should-generate-keys", is_flag=True, default=False, help="Specify to generate keys after creating .taf directory.")
    @click.option("--keystore", default=None, help="Location of the keystore directory. Can be specified in keys-description dictionary")
    @click.option("--keys-description", help="A dictionary containing information about the keys or a path to a json file which stores the needed information")
    @click.command(help="Create a .taf directory")
    def _init_command(path,should_generate_keys,keystore,keys_description):
        init(path,should_generate_keys,keystore, keys_description)
    return _init_command


def attach_to_group(group):
    conf_group = click.Group(name='conf')
    conf_group.add_command(init_command(), name='init')
    group.add_command(conf_group)


@click.group()
def cli():
    pass


attach_to_group(cli)

if __name__ == '__main__':
    cli()
