import click
from taf.tools.cli.lazy_group import LazyGroup


def taf_command_loader(name):
    if name != "yubikey":
        if name in (
            "dependencies",
            "keystore",
            "conf",
            "targets",
            "metadata",
            "roles",
            "repo",
        ):
            return f"taf.tools.{name}.attach_to_group"
        else:
            raise RuntimeError(f"Unknown command: {name}")
    try:
        import ykman  # noqa: F401

        return "taf.tools.yubikey.attach_to_group"
    except ImportError:
        pass


@click.group(
    cls=LazyGroup,
    lazy_subcommands={
        "dependencies": lambda: taf_command_loader("dependencies"),
        "keystore": lambda: taf_command_loader("keystore"),
        "conf": lambda: taf_command_loader("conf"),
        "repo": lambda: taf_command_loader("repo"),
        "targets": lambda: taf_command_loader("targets"),
        "metadata": lambda: taf_command_loader("metadata"),
        "roles": lambda: taf_command_loader("roles"),
        "yubikey": lambda: taf_command_loader("yubikey"),
    },
)
@click.version_option()
def taf():
    """TAF Command Line Interface"""
    pass


if __name__ == "__main__":
    taf()
