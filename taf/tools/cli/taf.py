import click
from taf.tools.cli.lazy_group import LazyGroup


@click.group(cls=LazyGroup, lazy_subcommands={
    "dependencies": "taf.tools.dependencies.attach_to_group",
    "keystore": "taf.tools.keystore.attach_to_group",
    "conf": "taf.tools.conf.attach_to_group",
    "repo": "taf.tools.repo.attach_to_group",
    "targets": "taf.tools.targets.attach_to_group",
    "metadata": "taf.tools.metadata.attach_to_group",
    "roles": "taf.tools.roles.attach_to_group",
    "yubikey": "taf.tools.yubikey.attach_to_group",
    "scripts": "taf.tools.scripts.attach_to_group",
})
@click.version_option()
def taf():
    """TAF Command Line Interface"""
    pass


if __name__ == '__main__':
    taf()
