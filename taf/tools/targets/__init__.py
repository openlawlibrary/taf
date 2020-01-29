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
        inside the targets directory of the authentication repository. Once the targets
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
                  "Authentication repo is presumed to be at root-dir/namespace/auth-repo-name")
    @click.option("--namespace", default=None, help="Namespace of the target repositories. "
                  "If omitted, it will be assumed that namespace matches the name of the "
                  "directory which contains the authentication repository")
    @click.option("--add-branch", default=False, is_flag=True, help="Whether to add name of "
                  "the current branch to target files")
    def update_repos_from_fs(path, root_dir, namespace, add_branch):
        """
        Update target files corresponding to target repositories by traversing through the root
        directory. Does not automatically sign the metadata files.
        Note: if repositories.json exists, it is better to call update_repos_from_repositories_json

        Target repositories are expected to be inside a directory whose name is equal to the specified
        namespace and which is located inside the root directory. If root directory is E:\\examples\\root
        and namespace is namespace1, target repositories should be in E:\\examples\\root\\namespace1.
        If the authentication repository and the target repositories are in the same root directory and
        the authentication repository is also directly inside a namespace directory, then the common root
        directory is calculated as two repositories up from the authentication repository's directory.
        Authentication repository's namespace can, but does not have to be equal to the namespace of target,
        repositories. If the authentication repository's path is E:\\root\\namespace\\auth-repo, root
        directory will be determined as E:\\root. If this default value is not correct, it can be redefined
        through the --root-dir option. If the --namespace option's value is not provided, it is assumed
        that the namespace of target repositories is equal to the authentication repository's namespace,
        determined based on the repository's path. E.g. Namespace of E:\\root\\namespace2\\auth-repo
        is namespace2.

        Once the directory containing all target directories is determined, it is traversed through all
        git repositories in that directory, apart from the authentication repository if it is found.
        For each found repository the current top commit and branch (if called with the
        --add-branch flag) are written to the corresponding target files. Target files are files
        inside the authentication repository's target directory. For example, for a target repository
        namespace1/target1, a file called target1 is created inside the targets/namespace1 authentication
        repository's direcotry.
        """
        developer_tool.update_target_repos_from_fs(path, root_dir, namespace, add_branch)

    @targets.command()
    @click.argument("path")
    @click.option("--root-dir", default=None, help="Directory where target repositories and, "
                  "optionally, authentication repository are located. If omitted it is "
                  "calculated based on authentication repository's path. "
                  "Authentication repo is presumed to be at root-dir/namespace/auth-repo-name")
    @click.option("--namespace", default=None, help="Namespace of the target repositories. "
                  "If omitted, it will be assumed that namespace matches the name of the "
                  "directory which contains the authentication repository")
    @click.option("--add-branch", default=False, is_flag=True, help="Whether to add name of "
                  "the current branch to target files")
    def update_repos_from_repositories_json(path, root_dir, namespace, add_branch):
        """
        Update target files corresponding to target repositories by traversing through repositories
        specified in repositories.json which are located inside the specified targets directory without
        signing the metadata files.

        Target repositories are expected to be inside a directory whose name is equal to the specified
        namespace and which is located inside the root directory. If root directory is E:\\examples\\root
        and namespace is namespace1, target repositories should be in E:\\examples\\root\\namespace1.
        If the authentication repository and the target repositories are in the same root directory and
        the authentication repository is also directly inside a namespace directory, then the common root
        directory is calculated as two repositories up from the authentication repository's directory.
        Authentication repository's namespace can, but does not have to be equal to the namespace of target,
        repositories. If the authentication repository's path is E:\\root\\namespace\\auth-repo, root
        directory will be determined as E:\\root. If this default value is not correct, it can be redefined
        through the --root-dir option. If the --namespace option's value is not provided, it is assumed
        that the namespace of target repositories is equal to the authentication repository's namespace,
        determined based on the repository's path. E.g. Namespace of E:\\root\\namespace2\\auth-repo
        is namespace2.

        Once the directory containing all target directories is determined, it is traversed through all
        git repositories in that directory which are listed in repositories.json.
        This means that for each found repository the current top commit and branch (if called with the
        --add-branch flag) are written to the target corresponding target files. Target files are files
        inside the authentication repository's target directory. For example, for a target repository
        namespace1/target1, a file called target1 is created inside the targets/namespace1
        authentication repo direcotry.
        """
        developer_tool.update_target_repos_from_repositories_json(path, root_dir, namespace, add_branch)
