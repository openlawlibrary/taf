import click
import taf.developer_tool as developer_tool
from taf.constants import DEFAULT_RSA_SIGNATURE_SCHEME


def attach_to_group(group):

    @group.group()
    def targets():
        pass

    @targets.command()
    @click.argument("path")
    @click.option("--keystore", default=None, help="Location of the keystore files")
    @click.option("--scheme", default=DEFAULT_RSA_SIGNATURE_SCHEME, help="A signature scheme "
                  "used for signing")
    def sign(path, keystore, scheme):
        """
        Register and sign target files. This means that the targets metadata file
        is updated by adding or editing information about all target files located
        inside the targets directory of the authenticatino repository. Once the targets
        file is updated, so are snapshot and timestamp. All files are signed. If the
        keystore parameter is provided, keys stored in that directory will be used for
        signing. If a needed key is not in that directory, the file can either be signed
        sy manually entering the key or by using a yubikey.
        """
        developer_tool.register_target_files(path, keystore=keystore, scheme=scheme)

    @targets.command()
    @click.argument("path")
    @click.option("--root-dir", default=None, help="Directory where target repositories and, "
                  "optionally, authentication repository are located. If omitted it is "
                  "calculated based on authentication repository's path. "
                  "Authentication repo is persumed to be at root-dir/namespace/auth-repo-name")
    @click.option("--namespace", default=None, help="Namespace of the target repositories. "
                  "If omitted, it will be assumed that namespace matches the name of the "
                  "directory which contains the authentication repository")
    @click.option("--add-branch", default=False, is_flag=True, help="Whether to add name of "
                  "the current branch to target files")
    def update_repos_from_fs(path, root_dir, namespace, add_branch):
        """
        Update target files corresonding to target repositories by traversing through the specified
        targets directory without signing the metadata files.
        Note: if repositories.json exists, it is better to call update_repos_from_repositories_json

        Traverses through all git repositories in the targets directory, apart from the authentication
        repository if it is also in that directory, and creates or updates target files. This means
        that for each found repository the current top commit and branch (if called with the
        --add-branch flag) are written to the target corresponding target files. Target files
        are files inside the authentication repository's target directory. For example, for
        a target repository namespace1/target1, a file called target1 is created inside
        the target/namespace1 authentication repo direcotry.
        """
        developer_tool.update_target_repos_from_fs(path, root_dir, namespace, add_branch)

    @targets.command()
    @click.argument("path")
    @click.option("--root-dir", default=None, help="Directory where target repositories and, "
                  "optionally, authentication repository are located. If omitted it is "
                  "calculated based on authentication repository's path. "
                  "Authentication repo is persumed to be at root-dir/namespace/auth-repo-name")
    @click.option("--namespace", default=None, help="Namespace of the target repositories. "
                  "If omitted, it will be assumed that namespace matches the name of the "
                  "directory which contains the authentication repository")
    @click.option("--add-branch", default=False, is_flag=True, help="Whether to add name of "
                  "the current branch to target files")
    def update_repos_from_repositories_json(path, root_dir, namespace, add_branch):
        """
        Update target files corresonding to target repositories by traversing through repositories
        specified in repositories.json which are located inside the specified targets directory without
        signing the metadata files.

        Traverses through all git repositories in the targets directory which are specified
        in repositories.json and creates or updates target files. This means that for each found
        repository the current top commit and branch (if called with the --add-branch flag)
        are written to the target corresponding target files. Target files are files inside the
        authentication repository's target directory. For example, for a target repository
        namespace1/target1, a file called target1 is created inside the target/namespace1
        authentication repo direcotry.
        """
        developer_tool.update_target_repos_from_repositories_json(path, root_dir, namespace, add_branch)
