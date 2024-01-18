import click
import json
from taf.api.repository import create_repository
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


def attach_to_group(group):

    @group.group()
    def repo():
        pass

    @repo.command()
    @catch_cli_exception(handle=TAFError)
    @click.option("--path", default=".", help="Authentication repository's location. If not specified, set to the current directory")
    @click.option("--keys-description", help="A dictionary containing information about the "
                  "keys or a path to a json file which stores the needed information")
    @click.option("--keystore", default=None, help="Location of the keystore files")
    @click.option("--no-commit", is_flag=True, default=False, help="Indicates if the changes should be "
                  "committed automatically")
    @click.option("--test", is_flag=True, default=False, help="Indicates if the created repository "
                  "is a test authentication repository")
    def create(path, keys_description, keystore, no_commit, test):
        """
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
                print(json.dumps({
                    'updateSuccessful': True
                }))
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
                print(json.dumps({
                    'updateSuccessful': True
                }))
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
    @click.option("--library-dir", default=None, help="Directory where target repositories and, "
                  "optionally, authentication repository are located. If omitted it is "
                  "calculated based on authentication repository's path. "
                  "Authentication repo is presumed to be at library-dir/namespace/auth-repo-name")
    @click.option("--from-commit", default=None, help="First commit which should be validated.")
    @click.option("--exclude-target", multiple=True, help="globs defining which target repositories should be "
                  "ignored during update.")
    @click.option("--strict", is_flag=True, default=False, help="Enable/disable strict mode - return an error"
                  "if warnings are raised")
    def validate(path, library_dir, from_commit, exclude_target, strict):
        """
        Validates an authentication repository which is already on the file system
        and its target repositories (which are also expected to be on the file system).
        Does not clone repositories, fetch changes or merge commits.

        Validation can be in strict or no-strict mode. Strict mode is set by specifying --strict, which will raise errors
        during validate if any/all warnings are found. By default, --strict is disabled.
        """
        validate_repository(path, library_dir, from_commit, exclude_target, strict)
