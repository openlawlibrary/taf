import importlib
import click

class LazyGroup(click.Group):
    def __init__(self, *args, lazy_subcommands=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.lazy_subcommands = lazy_subcommands or {}

    def list_commands(self, ctx):
        return super().list_commands(ctx) + sorted(self.lazy_subcommands.keys())

    def get_command(self, ctx, cmd_name):
        if cmd_name in self.lazy_subcommands:
            return self._lazy_load(cmd_name)
        return super().get_command(ctx, cmd_name)

    def _lazy_load(self, cmd_name):
        module_name, function_name = self.lazy_subcommands[cmd_name].rsplit(".", 1)
        module = importlib.import_module(module_name)
        function = getattr(module, function_name)
        group = click.Group(name=cmd_name)
        function(group)
        return group