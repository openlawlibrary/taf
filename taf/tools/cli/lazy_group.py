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
        function = self.lazy_subcommands[cmd_name]()
        if not function:
            return
        module_name, function_name = function.rsplit(".", 1)
        module = importlib.import_module(module_name)
        function = getattr(module, function_name)
        group = click.Group(name=cmd_name)
        function(group)
        return group

    def format_commands(self, ctx, formatter):
        rows = []
        sub_commands = set(self.lazy_subcommands.keys())
        loaded_commands = set(super().list_commands(ctx))

        for subcommand in sorted(loaded_commands | sub_commands):
            if subcommand in self.lazy_subcommands:
                # Load the command to get its help text
                cmd = self._lazy_load(subcommand)
            else:
                cmd = self.get_command(ctx, subcommand)
            if cmd is None:
                continue

            help = cmd.get_short_help_str()
            rows.append((subcommand, help))

        if rows:
            with formatter.section("Commands"):
                formatter.write_dl(rows)
