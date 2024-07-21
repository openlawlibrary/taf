import click
import importlib


@click.group()
@click.version_option()
def olc():
    """TAF Command Line Interface"""
    pass


def lazy_load_repo_cli():
    repo_cli = importlib.import_module('taf.tools.repo')
    repo_cli.attach_to_group(olc)


# Attach the lazy loader
lazy_load_repo_cli()


if __name__ == '__main__':
    olc()
