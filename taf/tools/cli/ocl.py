import click
import taf.tools.repo as repo_cli


@click.group()
def ocl():
    """TAF Command Line Interface"""
    pass


repo_cli.attach_to_group(ocl)


ocl()
