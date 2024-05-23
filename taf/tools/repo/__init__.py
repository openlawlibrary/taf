import click
import json
from taf.api.repository import create_repository, taf_status
from taf.exceptions import TAFError, UpdateFailedError
from taf.tools.cli import catch_cli_exception
from taf.updater.types.update import UpdateType
from taf.updater.updater import OperationType, RepositoryConfig, clone_repository, update_repository, validate_repository


def common_update_options(f):
    f = click.option("--expected-repo-type", default="either", type=click.Choice(["test", "official", "either"]), help="Indicates expected authentication repository type - test or official.")(f)
    f = click.option("--scripts-root-dir", default=None, help="Scripts root directory, which can be used to move scripts out of the authentication repository for testing purposes.")(f)
    f = click.option("--profile", is_flag=True, help="Flag used to run profiler and generate .prof file")(f)
    f = click.option("--format-output", is_flag=True, help="Return formatted output which includes information on if build was successful and error message if it was raised")(f)
    f = click.option("--exclude-target", multiple=True, help="Globs defining which target repositories should be ignored during update.")(f)
    f = click.option("--strict", is_flag=True, default=False, help="Enable/disable strict mode - return an error if warnings are raised.")(f)
    return f


def start_profiling():
    import cProfile
    import atexit

    print("Profiling...")
    pr = cProfile.Profile()
    pr.enable()

    def exit_profiler():
        pr.disable()
        print("Profiling completed")
        filename = 'updater.prof'  # You can change the filename if needed
        pr.dump_stats(filename)

    atexit.register(exit_profiler)


@click.group()
def repo():
    pass


@repo.command()
@catch_cli_exception(handle=TAFError)
@click.option("--path", default=".", help="Location of the auth repository, defaults to current directory")
@click.option("--keys-description", help="Dictionary or path to JSON file with key info")
@click.option("--keystore", default=None, help="Location of keystore files")
@click.option("--no-commit", is_flag=True, default=False, help="Do not commit changes automatically")
@click.option("--test", is_flag=True, default=False, help="Create a test authentication repository")
def create(path, keys_description, keystore, no_commit, test):
    """
    Create a new authentication repository at the exact location by registering signing keys and
    generating initial metadata files.
    """
    create_repository(
        path=path,
        keystore=keystore,
        roles_key_infos=keys_description,
        commit=not no_commit,
        test=test,
    )


@repo.command()
@catch_cli_exception(handle=UpdateFailedError)
@click.argument("url")
@common_update_options
@click.option("--path", help="Authentication repository's location. If not specified, calculated by combining repository's name specified in info.json and library dir")
@click.option("--library-dir", default=None, help="Directory where target repositories and, optionally, authentication repository are located. If not specified, set to the current directory")
@click.option("--from-fs", is_flag=True, default=False, help="Indicates if we want to clone a repository from the filesystem")
def clone(path, url, library_dir, from_fs, expected_repo_type,
          scripts_root_dir, profile, format_output, exclude_target, strict):
    """
    Validate and clone the authentication repository and target repositories. URL of the
    remote authentication repository must be specified when calling this command.
    """
    if profile:
        start_profiling()

    config = RepositoryConfig(
        operation=OperationType.CLONE,
        url=url,
        path=path,
        library_dir=library_dir,
        update_from_filesystem=from_fs,
        expected_repo_type=UpdateType(expected_repo_type),
        scripts_root_dir=scripts_root_dir,
        excluded_target_globs=exclude_target,
        strict=strict
    )

    try:
        clone_repository(config)
        if format_output:
            print(json.dumps({'updateSuccessful': True}))
    except Exception as e:
        if format_output:
            error_data = {
                'updateSuccessful': False,
                'error': str(e)
            }
            print(json.dumps(error_data))
        else:
            raise e


@repo.command()
@catch_cli_exception(handle=UpdateFailedError)
@common_update_options
@click.option("--path", default=None, help="Authentication repository's location. If not specified, set to the current directory")
@click.option("--library-dir", default=None, help="Directory where target repositories and, optionally, authentication repository are located. If not specified, calculated based on the authentication repository's path")
def update(path, library_dir, expected_repo_type,
           scripts_root_dir, profile, format_output, exclude_target, strict):
    """
    Update and validate the local authentication repository and target repositories.
    """
    if profile:
        start_profiling()

    config = RepositoryConfig(
        operation=OperationType.UPDATE,
        path=path,
        library_dir=library_dir,
        expected_repo_type=UpdateType(expected_repo_type),
        scripts_root_dir=scripts_root_dir,
        excluded_target_globs=exclude_target,
        strict=strict
    )

    try:
        update_repository(config)
        if format_output:
            print(json.dumps({'updateSuccessful': True}))
    except Exception as e:
        if format_output:
            error_data = {
                'updateSuccessful': False,
                'error': str(e)
            }
            print(json.dumps(error_data))
        else:
            raise e


@repo.command()
@click.option("--path", default=".", help="Authentication repository's location. If not specified, set to the current directory")
@click.option("--library-dir", default=None, help="Directory where target repositories and, optionally, authentication repository are located. If omitted it is calculated based on authentication repository's path. Authentication repo is presumed to be at library-dir/namespace/auth-repo-name")
@click.option("--from-commit", default=None, help="First commit which should be validated.")
@click.option("--exclude-target", multiple=True, help="globs defining which target repositories should be ignored during update.")
@click.option("--strict", is_flag=True, default=False, help="Enable/disable strict mode - return an error if warnings are raised")
def validate(path, library_dir, from_commit, exclude_target, strict):
    """
    Validates an authentication repository which is already on the file system and its target repositories.
    """
    validate_repository(path, library_dir, from_commit, exclude_target, strict)


@repo.command()
@catch_cli_exception(handle=TAFError)
@click.option("--path", default=".", help="Authentication repository's location. If not specified, set to the current directory")
@click.option("--library-dir", default=None, help="Path to the library's root directory. Determined based on the authentication repository's path if not provided.")
def status(path, library_dir):
    """
    Print the status of the authentication repository including its dependencies and target repositories.
    """
    try:
        taf_status(path, library_dir)
    except TAFError as e:
        click.echo()
        click.echo(str(e))
        click.echo()


def attach_to_group(group):
    group.add_command(repo)
