import click
from taf.api.targets import (
    list_targets,
    add_target_repo,
    register_target_files,
    remove_target_repo,
    export_targets_history,
    update_and_sign_targets,
    update_target_repos_from_repositories_json
)
from taf.constants import DEFAULT_RSA_SIGNATURE_SCHEME
from taf.exceptions import TAFError
from taf.repository_utils import find_valid_repository
from taf.tools.cli import catch_cli_exception, process_custom_command_line_args


def add_repo_command():
    @click.command(context_settings=dict(
        ignore_unknown_options=True,
        allow_extra_args=True,
    ), help="""Add a new repository by adding it to repositories.json, creating a delegation (if targets is not
        its signing role) and adding and signing initial target files if the repository is found on the filesystem.
        All additional information that should be saved as the repository's custom content in `repositories.json`
        is specified by providing additional options. If the signing role does not exist, it will be created.
        E.g.

        `taf targets add-repo --path auth-path --target-name namespace1/repo --serve latest --role role1`

        or

        `taf targets add-repo --target-name namespace1/repo --serve latest --role role1`

        if directly inside the authentication repository.

        In this case, serve: latest will be added to the custom part of the target repository's entry in
        repositories.json.

        If the repository does not exist, it is sufficient to provide its namespace prefixed name
        instead of the full filesystem path. If the repository's path is not provided, it is expected
        to be located in the same library root directory as the authentication repository,
        in a directory whose name corresponds to its name. If authentication repository's path
        is `E:\\examples\\root\\namespace\\auth`, and the target's namespace prefixed name is
        `namespace1\\repo1`, the target's path will be set to `E:\\examples\\root\\namespace1\\repo1`.""")
    @catch_cli_exception(handle=TAFError)
    @click.option("--path", default=".", help="Authentication repository's location. If not specified, set to the current directory")
    @click.argument("target-name")
    @click.option("--target-path", default=None, help="Target repository's filesystem path")
    @click.option("--role", default="targets", help="Signing role of the corresponding target file. Can be a new role, in which case it will be necessary to enter its information when prompted")
    @click.option("--keystore", default=None, help="Location of the keystore files")
    @click.option("--prompt-for-keys", is_flag=True, default=False, help="Whether to ask the user to enter their key if not located inside the keystore directory")
    @click.option("--no-commit", is_flag=True, default=False, help="Indicates that the changes should not be committed automatically")
    @click.pass_context
    def add_repo(ctx, path, target_path, target_name, role, keystore, prompt_for_keys, no_commit):
        path = find_valid_repository(path)
        custom = process_custom_command_line_args(ctx)
        add_target_repo(
            path=path,
            target_path=target_path,
            target_name=target_name,
            library_dir=None,
            role=role,
            keystore=keystore,
            custom=custom,
            prompt_for_keys=prompt_for_keys,
            commit=not no_commit
        )
    return add_repo


def export_history_command():
    @click.command(help="""Export lists of sorted commits, grouped by branches and target repositories, based
        on target files stored in the authentication repository. If commit is specified,
        only return changes made at that revision and all subsequent revisions. If it is not,
        start from the initial authentication repository commit.
        Repositories which will be taken into consideration when collecting targets historical
        data can be defined using the repo option. If no repositories are passed in, historical
        data will include all target repositories.
        to a file whose location is specified using the output option, or print it to
        console.""")
    @click.option("--path", default=".", help="Authentication repository's location. If not specified, set to the current directory")
    @click.option("--commit", default=None, help="Starting authentication repository commit")
    @click.option("--output", default=None, help="File to which the resulting json will be written. If not provided, the output will be printed to console")
    @click.option("--repo", multiple=True, help="Target repository whose historical data should be collected")
    def export_history(path, commit, output, repo):
        path = find_valid_repository(path)
        export_targets_history(path, commit, output, repo)
    return export_history


def list_targets_command():
    @click.command(help="""List target repositories of the specified authentication repository. All target repositories
        are expected to be inside the same library root dir. Only repositories that are listed in
        repositories.json and whose corresponding target files exist (files whose name matched the
        name defined in repositories.json located inside the targets directory). For each repository,
        print:
        - if unauthenticated commits are allowed
        - if they exist on the user's local machine inside the library root dir (if they were cloned)
        - if they are bare
        - if there are unsigned changes (commits not registered in the authentication repository)
        - if they are up-to-date with remote
        - if there are uncommitted changes""")
    @click.option("--path", default=".", help="Authentication repository's location. If not specified, set to the current directory")
    @click.option("--library-dir", default=None, help="Directory where target repositories and, optionally, authentication repository are located. If omitted it is calculated based on authentication repository's path. Authentication repo is presumed to be at library-dir/namespace/auth-repo-name")
    def list(path, library_dir):
        path = find_valid_repository(path)
        list_targets(path, library_dir)
    return list


def remove_repo_command():
    @click.command(help="Remove a target repository (from repsoitories.json and target file) and sign")
    @catch_cli_exception(handle=TAFError)
    @click.option("--path", default=".", help="Authentication repository's location. If not specified, set to the current directory")
    @click.argument("target-name")
    @click.option("--keystore", default=None, help="Location of the keystore files")
    @click.option("--prompt-for-keys", is_flag=True, default=False, help="Whether to ask the user to enter their key if not located inside the keystore directory")
    def remove_repo(path, target_name, keystore, prompt_for_keys):
        path = find_valid_repository(path)
        remove_target_repo(
            path=path,
            target_name=target_name,
            keystore=keystore,
            prompt_for_keys=prompt_for_keys,
        )
    return remove_repo


def sign_targets_command():
    @click.command(help="""Register and sign target files. This means that all targets metadata files corresponding
        to roles responsible for updated target files are updated. Once the targets
        files are updated, so are snapshot and timestamp. All files are then signed. If the
        keystore parameter is provided, keys stored in that directory will be used for
        signing. If a needed key is not in that directory, the file can either be signed
        by manually entering the key or by using a Yubikey.""")
    @catch_cli_exception(handle=TAFError)
    @click.option("--path", default=".", help="Authentication repository's location. If not specified, set to the current directory")
    @click.option("--keystore", default=None, help="Location of the keystore files")
    @click.option("--keys-description", help="A dictionary containing information about the keys or a path to a json file which stores the needed information")
    @click.option("--scheme", default=DEFAULT_RSA_SIGNATURE_SCHEME, help="A signature scheme used for signing")
    @click.option("--prompt-for-keys", is_flag=True, default=False, help="Whether to ask the user to enter their key if not located inside the keystore directory")
    @click.option("--no-commit", is_flag=True, default=False, help="Indicates that the changes should not be committed automatically")
    def sign(path, keystore, keys_description, scheme, prompt_for_keys, no_commit):
        try:
            path = find_valid_repository(path)
            register_target_files(
                path=path,
                keystore=keystore,
                roles_key_infos=keys_description,
                scheme=scheme,
                write=True,
                prompt_for_keys=prompt_for_keys,
                commit=not no_commit
            )
        except TAFError as e:
            click.echo()
            click.echo(str(e))
            click.echo()
    return sign


def update_and_sign_command():
    @click.command(help="""Update target files corresponding to target repositories specified through the target type parameter
        by writing the current top commit and branch name to the target files. Sign the updated files
        and then commit. Types are expected to be defined in reposoitories.json, inside the custom data
        (Should be generalized in the future). If types are not specified, update all repositories specified
        in repositories.json.

        Target repositories are expected to be inside a directory whose name is equal to the specified
        namespace and which is located inside the root directory. If root directory is E:\\examples\\root
        and namespace is namespace1, target repositories should be in E:\\examples\\root\\namespace1.
        If the authentication repository and the target repositories are in the same root directory and
        the authentication repository is also directly inside a namespace directory, then the common root
        directory is calculated as two repositories up from the authentication repository's directory.
        Authentication repository's namespace can, but does not have to be equal to the namespace of target,
        repositories. If the authentication repository's path is E:\\root\\namespace\\auth-repo, root
        directory will be determined as E:\\root. If this default value is not correct, it can be redefined
        through the --library-dir option. If the --namespace option's value is not provided, it is assumed
        that the namespace of target repositories is equal to the authentication repository's namespace,
        determined based on the repository's path. E.g. Namespace of E:\\root\\namespace2\\auth-repo
        is namespace2.""")
    @catch_cli_exception(handle=TAFError)
    @click.option("--path", default=".", help="Authentication repository's location. If not specified, set to the current directory")
    @click.option("--library-dir", default=None, help="Directory where target repositories and, optionally, authentication repository are located. If omitted it is calculated based on authentication repository's path. Authentication repo is presumed to be at library-dir/namespace/auth-repo-name")
    @click.option("--target-type", multiple=True, help="Types of target repositories whose corresponding target files should be updated and signed. Should match a target type defined in repositories.json")
    @click.option("--keystore", default=None, help="Location of the keystore files")
    @click.option("--keys-description", help="A dictionary containing information about the keys or a path to a json file which stores the needed information")
    @click.option("--scheme", default=DEFAULT_RSA_SIGNATURE_SCHEME, help="A signature scheme used for signing")
    @click.option("--prompt-for-keys", is_flag=True, default=False, help="Whether to ask the user to enter their key if not located inside the keystore directory")
    @click.option("--no-commit", is_flag=True, default=False, help="Indicates that the changes should not be committed automatically")
    def update_and_sign(path, library_dir, target_type, keystore, keys_description, scheme, prompt_for_keys, no_commit):
        try:
            path = find_valid_repository(path)
            if len(target_type):
                update_and_sign_targets(
                    path,
                    library_dir,
                    target_type,
                    keystore=keystore,
                    roles_key_infos=keys_description,
                    scheme=scheme,
                    prompt_for_keys=prompt_for_keys,
                    commit=not no_commit,
                )
            else:
                update_target_repos_from_repositories_json(
                    path,
                    library_dir,
                    add_branch=True,
                    keystore=keystore,
                    scheme=scheme,
                    prompt_for_keys=prompt_for_keys,
                    commit=not no_commit
                )
        except TAFError as e:
            click.echo()
            click.echo(str(e))
            click.echo()
    return update_and_sign


def attach_to_group(group):

    group.add_command(add_repo_command(), name='add-repo')
    group.add_command(export_history_command(), name='export-history')
    group.add_command(list_targets_command(), name='list')
    group.add_command(remove_repo_command(), name='remove-repo')
    group.add_command(sign_targets_command(), name='sign')
    group.add_command(update_and_sign_command(), name='update-and-sign')
