import shutil
import sys
import click
from functools import partial, wraps
from logging import ERROR
from logdecorator import log_on_error

from taf.exceptions import InvalidRepositoryError, TAFError
from taf.log import taf_logger
from taf.repository_utils import find_valid_repository
from taf.git import GitRepository
from taf.utils import is_run_from_python_executable, on_rm_error


def catch_cli_exception(func=None, *, handle=TAFError, print_error=False, remove_dir_on_error=False, skip_cleanup=False):
    if not func:
        return partial(
            catch_cli_exception,
            handle=handle,
            print_error=print_error,
            remove_dir_on_error=remove_dir_on_error,
            skip_cleanup=skip_cleanup,
        )

    handle = tuple(handle) if isinstance(handle, (list, tuple)) else (handle,)

    @wraps(func)
    def wrapper(*args, **kwargs):
        successful = False
        try:
            result = func(*args, **kwargs)
            successful = True
            return result
        except handle as e:
            if print_error:
                click.echo(e)
        except Exception as e:
            if is_run_from_python_executable():
                click.echo(f"An error occurred: {e}")
                sys.exit(1)
            else:
                raise e
        finally:
            if not skip_cleanup and not successful and "path" in kwargs:
                path = kwargs["path"]
                repo = GitRepository(path=path)
                if repo.is_git_repository and not repo.is_bare_repository:
                    repo.clean_and_reset()
                if remove_dir_on_error:
                    shutil.rmtree(path, onerror=on_rm_error)

    return wrapper


def find_repository(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            if "path" in kwargs:
                kwargs["path"] = find_valid_repository(kwargs["path"])
            return func(*args, **kwargs)
        except InvalidRepositoryError as e:
            click.echo(f"An error occurred: {e}")
            sys.exit(1)

    return wrapper


@log_on_error(
    ERROR,
    "{e}",
    logger=taf_logger,
    on_exceptions=TAFError,
    reraise=True,
)
def process_custom_command_line_args(ctx):
    """
    Certain cli commands need to make it possible to enter custom arguments.
    E.g. when adding a new target repository, users can specify using the cli
    key-value pairs that will be written to its custom section of repositories.json.
    This function checks if that input is valid. It is easy to accidentally omit a space,
    e.g. --arg1 val1--arg2 val2. So show a nice error message in such a case. Also convert
    boolean values to actual booleans.

    Arguments:
        ctx: click context

    Returns:
       A dictionary containing parsed custom arguments
    """

    def _convert_value(value):
        if value.lower() == "true":
            return True
        if value.lower() == "false":
            return False
        return value

    if len(ctx.args) % 2 == 1:
        raise TAFError(
            "Custom parameters invalid. Check if there are spaces around each parameter/value"
        )

    custom = (
        {
            ctx.args[i][2:]: _convert_value(ctx.args[i + 1])
            for i in range(0, len(ctx.args), 2)
        }
        if len(ctx.args)
        else {}
    )
    return custom
