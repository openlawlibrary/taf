import click
import taf.tools.repo as repo_cli


@click.group()
def olc():
    """TAF Command Line Interface"""
    pass


repo_cli.attach_to_group(olc)


olc()
