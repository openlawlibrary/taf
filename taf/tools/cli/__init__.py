import click
from functools import partial, wraps


def catch_cli_exception(func=None, *, handle, print_error=False):
    if not func:
        return partial(catch_cli_exception, handle=handle)

    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except handle as e:
            if print_error:
                click.echo(e)

    return wrapper
