import click
import taf.tools.keystore as keystore_cli
import taf.tools.repo as repo_cli
import taf.tools.targets as targets_cli
import taf.tools.metadata as metadata_cli
import taf.tools.yubikey as yubikey_cli


@click.group()
def taf():
    """TAF Command Line Interface"""
    pass


keystore_cli.attach_to_group(taf)
repo_cli.attach_to_group(taf)
targets_cli.attach_to_group(taf)
metadata_cli.attach_to_group(taf)
yubikey_cli.attach_to_group(taf)


taf()
