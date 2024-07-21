import click
import importlib


@click.group()
@click.version_option()
def taf():
    """TAF Command Line Interface"""
    pass


def lazy_load_dependencies():
    module = importlib.import_module('taf.tools.dependencies')
    module.attach_to_group(taf)


def lazy_load_keystore():
    module = importlib.import_module('taf.tools.keystore')
    module.attach_to_group(taf)


def lazy_load_conf():
    module = importlib.import_module('taf.tools.conf')
    module.attach_to_group(taf)


def lazy_load_repo():
    module = importlib.import_module('taf.tools.repo')
    module.attach_to_group(taf)


def lazy_load_targets():
    module = importlib.import_module('taf.tools.targets')
    module.attach_to_group(taf)


def lazy_load_metadata():
    module = importlib.import_module('taf.tools.metadata')
    module.attach_to_group(taf)


def lazy_load_roles():
    module = importlib.import_module('taf.tools.roles')
    module.attach_to_group(taf)


def lazy_load_yubikey():
    try:
        module = importlib.import_module('taf.tools.yubikey')
        module.attach_to_group(taf)
    except ImportError:
        pass


# Attach the lazy loaders
lazy_load_dependencies()
lazy_load_keystore()
lazy_load_conf()
lazy_load_repo()
lazy_load_targets()
lazy_load_metadata()
lazy_load_roles()
lazy_load_yubikey()

if __name__ == '__main__':
    taf()
