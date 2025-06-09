import sys
import click
import json

from taf import settings
from taf.api.repository import create_repository, taf_status
from taf.auth_repo import AuthenticationRepository
from taf.exceptions import TAFError, UpdateFailedError
from taf.log import initialize_logger_handlers, taf_logger
from taf.tools.cli import catch_cli_exception, find_repository
from taf.updater.types.update import UpdateType
from taf.updater.updater import OperationType, UpdateConfig, clone_repository, update_repository, validate_repository
from taf.yubikey.yubikey_manager import pin_managed


def common_update_options(f):
    f = click.option("--expected-repo-type", default="either", type=click.Choice(["test", "official", "either"]), help="Indicates expected authentication repository type - test or official.")(f)
    f = click.option("--scripts-root-dir", default=None, help="Scripts root directory, which can be used to move scripts out of the authentication repository for testing purposes.")(f)
    f = click.option("--profile", is_flag=True, help="Flag used to run profiler and generate .prof file")(f)
    f = click.option("--format-output", is_flag=True, help="Return formatted output which includes information on if build was successful and error message if it was raised")(f)
    f = click.option("--exclude-target", multiple=True, help="Globs defining which target repositories should be ignored during update.")(f)
    f = click.option("--strict", is_flag=True, default=False, help="Enable/disable strict mode - return an error if warnings are raised.")(f)
    return f


def _call_updater(config, format_output):
    """
    A helper function which calls update or clone repository
    """
    try:
        if config.operation == OperationType.CLONE:
            updater_output = clone_repository(config)
        else:
            updater_output = update_repository(config)

        successful = updater_output["event"] == "event/succeeded"
        if format_output:
            if successful:
                print(json.dumps({'updateSuccessful': successful}, ))
            else:
                error = updater_output.get("error_msg", "")
                print(json.dumps({'updateSuccessful': successful, "error": error}))

        if not successful:
            sys.exit(1)
    except Exception as e:
        if format_output:
            error_data = {"updateSuccessful": False, "error": str(e)}
            taf_logger.error(json.dumps(error_data))
            sys.exit(1)
        else:
            sys.exit(1)


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


def create_repo_command():
    @click.command(help="""
        \b
        Create a new authentication repository at the specified location by registering
        signing keys and generating initial metadata files. Information about the roles
        can be provided through a dictionary - either specified directly or contained
        by a .json file whose path is specified when calling this command. This allows
        definition of:
            - total number of keys per role
            - threshold of signatures per role
            - should keys of a role be on Yubikeys or should keystore files be used
            - scheme (the default scheme is rsa-pkcs1v15-sha256)
            - keystore path, if not specified via keystore option

        \b
        For example:
        {
            "roles": {
                "root": {
                    "number": 3,
                    "length": 2048,
                    "passwords": ["password1", "password2", "password3"],
                    "threshold": 2,
                    "yubikey": true
                },
                "targets": {
                    "length": 2048
                },
                "snapshot": {},
                "timestamp": {}
            },
            "keystore": "keystore_path"
        }

        In cases when this dictionary is not specified, it is necessary to enter the needed
        information when asked to do so, or confirm that default values should be used.
        If keys should be stored in keystore files, it is possible to either use already generated
        keys (stored in keystore files located at the path specified using the keystore option),
        or to generate new one.

        If the test flag is set, a special target file will be created. This means that when
        calling the updater, it'll be necessary to use the --authenticate-test-repo flag.
        """)
    @catch_cli_exception(handle=TAFError, remove_dir_on_error=True)
    @click.argument("path", type=click.Path(exists=False, file_okay=False, dir_okay=True, writable=True))
    @click.option("--keys-description", help="A dictionary containing information about the "
                  "keys or a path to a json file which stores the needed information")
    @click.option("--keystore", default=None, help="Location of the keystore files")
    @click.option("--no-commit", is_flag=True, default=False, help="Indicates if the changes should be "
                  "committed automatically")
    @click.option("--test", is_flag=True, default=False, help="Indicates if the created repository "
                  "is a test authentication repository")
    @pin_managed
    def create(path, keys_description, keystore, no_commit, test, pin_manager):
        create_repository(
            path=path,
            pin_manager=pin_manager,
            keystore=keystore,
            roles_key_infos=keys_description,
            commit=not no_commit,
            test=test,
        )
    return create


def clone_repo_command():
    @click.command(help="""
        Validate and clone authentication repositories and target repositories. URL of the
        remote authentication repository must be specified when calling this command. If the remote repository's URL is a file system path, the --from-fs flag must be used.

        The path to the authentication repository directory either read from targets/protected/info.json
        or specified using the --path option. If targets/protected/info.json does not exist and path is not
        defined, an error will be raised.

        If the authentication repository and the target repositories are in the same root directory,
        the locations of the target repositories are calculated based on the authentication repository's
        path. If this is not the case, it is necessary to redefine this default value using the
        --library-dir option. For example, if the authentication repository's path is
        E:\\root\\namespace\\auth-repo, and --library-dir is not specified, E:\\root is assumed
        to be the root directory.

        The names of the target repositories (as defined in repositories.json) are appended to the root
        repository's path, thus defining the location of each target repository. For instance, if the
        names of the target repositories are namespace/repo1, namespace/repo2, etc., and the root
        directory is E:\\root, the paths of the target repositories will be calculated as
        E:\\root\\namespace\\repo1, E:\\root\\namespace\\repo2, etc.

        The --scripts-root-dir option can be used to move scripts out of the authentication repository for
        testing purposes (to avoid a dirty index). Scripts are expected to be located in the
        scripts_root_dir/repo_name directory.

        One or more target repositories can be excluded from the update process using the --exclude-target
        option. In this case, the library will only be partly validated, so the last_validated_commit will
        not be updated, and no scripts will be called.

        The update can be performed in strict or non-strict mode. Strict mode is enabled by specifying
        --strict, which will raise errors during the update if any warnings are found. By default, --strict
        is disabled.
        """)
    @catch_cli_exception(handle=UpdateFailedError, skip_cleanup=True)
    @click.argument("url")
    @common_update_options
    @click.option("--path", help="Authentication repository's location. If not specified, calculated by combining repository's name specified in info.json and library dir")
    @click.option("--library-dir", default=None, help="Directory where target repositories and, optionally, authentication repository are located. If not specified, set to the current directory")
    @click.option("--from-fs", is_flag=True, default=False, help="Indicates if we want to clone a repository from the filesystem")
    @click.option("--bare", is_flag=True, default=False, help="Clone repositories as bare repositories")
    @click.option("--no-deps", is_flag=True, default=False, help="Optionally disables updating of dependencies")
    @click.option("--upstream/--no-upstream", default=False, help="Skips comparison with remote repositories upstream")
    @click.option("-v", "--verbosity", count=True, help="Displays varied levels of logging information based on verbosity level")
    @click.option("--run-scripts/--no-run-scripts", default=False, help="Run the auxiliary lifecycle handler scripts.")
    def clone(path, url, library_dir, from_fs, expected_repo_type, scripts_root_dir, profile, format_output, exclude_target, strict, bare, upstream, no_deps, verbosity, run_scripts):
        settings.VERBOSITY = verbosity
        initialize_logger_handlers()
        if profile:
            start_profiling()

        config = UpdateConfig(
            operation=OperationType.CLONE,
            remote_url=url,
            path=path,
            library_dir=library_dir,
            update_from_filesystem=from_fs,
            expected_repo_type=UpdateType(expected_repo_type),
            scripts_root_dir=scripts_root_dir,
            excluded_target_globs=exclude_target,
            strict=strict,
            bare=bare,
            no_upstream=not upstream,
            no_deps=no_deps,
            run_scripts=run_scripts,
        )

        _call_updater(config, format_output)

    return clone


def update_repo_command():
    @click.command(help="""
        Update and validate local authentication repositories and target repositories.

        If the authentication repository and the target repositories are in the same root directory,
        the locations of the target repositories are calculated based on the authentication repository's
        path. If this is not the case, it is necessary to redefine this default value using the
        --library-dir option. This means that if the authentication repository's path is
        E:\\root\\namespace\\auth-repo, and --library-dir is not specified, E:\\root is assumed to be
        the root directory.

        The names of the target repositories (as defined in repositories.json) are appended to the root
        repository's path, thus defining the location of each target repository. For example, if the names
        of the target repositories are namespace/repo1, namespace/repo2, etc., and the root directory is
        E:\\root, the path of the target repositories will be calculated as E:\\root\\namespace\\repo1,
        E:\\root\\namespace\\repo2, etc.

        The path to the authentication repository directory is set by the --path option. If this option is
        not provided, the current directory is used.

        The --scripts-root-dir option can be used to move scripts out of the authentication repository for
        testing purposes (to avoid a dirty index). Scripts will then be expected to be located in the
        scripts_root_dir/repo_name directory.

        One or more target repositories can be excluded from the update process using the --exclude-target
        option. In this case, the library will only be partly validated, so the last_validated_commit will
        not be updated, and no scripts will be called.

        The update can be performed in strict or non-strict mode. Strict mode is enabled by specifying
        --strict, which will raise errors during the update if any warnings are found. By default, --strict
        is disabled.
        """)
    @find_repository
    @catch_cli_exception(handle=UpdateFailedError, skip_cleanup=True)
    @common_update_options
    @click.option("--path", default=".", help="Authentication repository's location. If not specified, set to the current directory")
    @click.option("--library-dir", default=None, help="Directory where target repositories and, optionally, authentication repository are located. If not specified, calculated based on the authentication repository's path")
    @click.option("--force", is_flag=True, default=False, help="Force Update repositories")
    @click.option("--no-deps", is_flag=True, default=False, help="Optionally disables updating of dependencies.")
    @click.option("--upstream/--no-upstream", default=False, help="Skips comparison with remote repositories upstream")
    @click.option("-v", "--verbosity", count=True, help="Displays varied levels of logging information based on verbosity level")
    @click.option("--run-scripts/--no-run-scripts", default=False, help="Run the auxiliary lifecycle handler scripts.")
    def update(path, library_dir, expected_repo_type, scripts_root_dir, profile, format_output, exclude_target, strict, no_deps, force, upstream, verbosity, run_scripts):
        settings.VERBOSITY = verbosity
        initialize_logger_handlers()

        if profile:
            start_profiling()

        config = UpdateConfig(
            operation=OperationType.UPDATE,
            path=path,
            library_dir=library_dir,
            expected_repo_type=UpdateType(expected_repo_type),
            scripts_root_dir=scripts_root_dir,
            excluded_target_globs=exclude_target,
            strict=strict,
            force=force,
            no_upstream=not upstream,
            no_deps=no_deps,
            run_scripts=run_scripts,
        )

        _call_updater(config, format_output)
    return update


def validate_repo_command():
    @click.command(help="""
        Validates an authentication repository which is already on the file system
        and its target repositories (which are also expected to be on the file system).
        Does not clone repositories, fetch changes or merge commits.

        Validation can be in strict or no-strict mode. Strict mode is set by specifying --strict, which will raise errors
        during validate if any/all warnings are found. By default, --strict is disabled.
        """)
    @find_repository
    @catch_cli_exception(handle=UpdateFailedError)
    @click.option("--path", default=".", help="Authentication repository's location. If not specified, set to the current directory")
    @click.option("--library-dir", default=None, help="Directory where target repositories and, "
                  "optionally, authentication repository are located. If omitted it is "
                  "calculated based on authentication repository's path. "
                  "Authentication repo is presumed to be at library-dir/namespace/auth-repo-name")
    @click.option("--from-commit", default=None, help="First commit which should be validated.")
    @click.option("--from-latest", is_flag=True, default=False, help="Use the last validated commit as the starting point.")
    @click.option("--exclude-target", multiple=True, help="globs defining which target repositories should be "
                  "ignored during update.")
    @click.option("--strict", is_flag=True, default=False, help="Enable/disable strict mode - return an error"
                  "if warnings are raised")
    @click.option("--no-targets", is_flag=True, default=False, help="Skips target repository validation and validates only authentication repositories")
    @click.option("--no-deps", is_flag=True, default=False, help="Optionally disables updating of dependencies")
    @click.option("-v", "--verbosity", count=True, help="Displays varied levels of logging information based on verbosity level")
    @click.option("--profile", is_flag=True, help="Flag used to run profiler and generate .prof file")
    def validate(path, library_dir, from_commit, from_latest, exclude_target, strict, no_targets, no_deps, verbosity, profile):
        settings.VERBOSITY = verbosity
        initialize_logger_handlers()
        if profile:
            start_profiling()
        auth_repo = AuthenticationRepository(path=path)
        bare = auth_repo.is_bare_repository
        if from_latest:
            from_commit = auth_repo.last_validated_commit
        validate_repository(path, library_dir, from_commit, exclude_target, strict, bare, no_targets, no_deps)
    return validate


def latest_commit_and_branch_command():
    @click.command(help="""Fetch and print the last validated commit hash and the default branch.
        Integrated into the pre-push git hook""")
    @find_repository
    @catch_cli_exception
    @click.option("--path", default=".", help="Authentication repository's location. If not specified, set to the current directory")
    def latest_commit_and_branch(path):
        auth_repo = AuthenticationRepository(path=path)
        last_validated_commit = auth_repo.last_validated_commit or ""
        default_branch = auth_repo.default_branch
        print(f"{default_branch},{last_validated_commit}")
    return latest_commit_and_branch


def status_command():
    @click.command(help="Prints the whole state of the library, including authentication repositories and its dependencies.")
    @find_repository
    @catch_cli_exception
    @click.option("--path", default=".", help="Authentication repository's location. If not specified, set to the current directory")
    @click.option("--library-dir", default=None, help="Path to the library's root directory. Determined based on the authentication repository's path if not provided.")
    def status(path, library_dir):
        try:
            taf_status(path, library_dir)
        except TAFError as e:
            click.echo()
            click.echo(f"Error: {e}")
            click.echo()
    return status


def attach_to_group(group):
    group.add_command(create_repo_command(), name='create')
    group.add_command(clone_repo_command(), name='clone')
    group.add_command(update_repo_command(), name='update')
    group.add_command(validate_repo_command(), name='validate')
    group.add_command(latest_commit_and_branch_command(), name='latest-commit-and-branch')
    group.add_command(status_command(), name='status')
