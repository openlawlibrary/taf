import click
from taf.tools.cli.lazy_group import LazyGroup


@click.group(cls=LazyGroup, lazy_subcommands={"repo": "taf.tools.repo.attach_to_group"})
@click.version_option()
def olc():
    """OLC Command Line Interface"""
    pass


if __name__ == "__main__":
    olc()
