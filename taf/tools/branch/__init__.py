import click

from taf.api.merge import merge_branch_commits
from taf.auth_repo import AuthenticationRepository
from taf.exceptions import TAFError
from taf.models.merge import (
    build_policy,
    locate_root_auth_repo,
    partner_name,
    resolve_policy,
)
from taf.tools.cli import catch_cli_exception, find_repository
from taf.yubikey.yubikey_manager import pin_managed


def merge_command():
    @click.command(
        name="merge",
        help="""
        Merge commits of a batch branch - a branch in the authentication repository
        whose commits each authenticate one commit of one or more target repositories,
        such as a speculative, publication or update branch - into each participating
        target repository's destination branch.

        Which repositories participate, what commit each merges to, its destination
        branch and any date gate are read directly from the authentication repository's
        signed target files. --policy selects a named policy (built in, or read from
        --config or a root authentication repository's signed merge-policies.json) that
        supplies the rest: the branch name pattern, and any capstone role rules.
        --branch-pattern is a config-free escape hatch that runs with a policy of just
        that pattern.
        """,
    )
    @find_repository
    @catch_cli_exception(handle=TAFError)
    @click.option(
        "--path",
        default=".",
        help="Authentication repository's location. If not specified, set to the current directory",
    )
    @click.option(
        "--library-dir",
        default=None,
        help="Directory containing the target repositories. If not specified, calculated based on the authentication repository's path",
    )
    @click.option(
        "--policy",
        "policy_name",
        default=None,
        help="Name of the merge policy to apply (e.g. speculative, rdf, update)",
    )
    @click.option(
        "--branch-pattern",
        default=None,
        help="Config-free escape hatch: run with a policy of just this branch pattern",
    )
    @click.option(
        "--config",
        "config_path",
        default=None,
        help="Path to a local merge-policies.json-shaped file",
    )
    @click.option(
        "--root-auth",
        "root_auth_path",
        default=None,
        help="Path to the root authentication repository whose signed targets/merge-policies.json should be used",
    )
    @click.option(
        "--pushed-branch",
        default=None,
        help="If given, this call is a no-op unless it matches the policy's branch pattern",
    )
    @click.option("--keystore", default=None, help="Location of the keystore files")
    @click.option(
        "--deploy",
        is_flag=True,
        default=False,
        help="Push changes to the remote after merging",
    )
    @click.option(
        "--git-access-token",
        default=None,
        help="Access token used to change a target repository's default branch",
    )
    @pin_managed
    def merge(
        path,
        library_dir,
        policy_name,
        branch_pattern,
        config_path,
        root_auth_path,
        pushed_branch,
        keystore,
        deploy,
        git_access_token,
        pin_manager,
    ):
        if branch_pattern:
            policy = build_policy(branch_pattern=branch_pattern)
        else:
            if not policy_name:
                raise click.UsageError(
                    "One of --policy or --branch-pattern is required"
                )
            root_auth_repo = None
            partner = None
            if config_path is None:
                root_auth_repo = locate_root_auth_repo(library_dir, root_auth_path)
                if root_auth_repo is not None:
                    partner = partner_name(AuthenticationRepository(path=path))
            policy = resolve_policy(
                policy_name,
                config_path=config_path,
                root_auth_repo=root_auth_repo,
                partner_name=partner,
            )

        merge_branch_commits(
            path=path,
            pin_manager=pin_manager,
            policy=policy,
            library_dir=library_dir,
            pushed_branch=pushed_branch,
            keystore=keystore,
            deploy=deploy,
            git_access_token=git_access_token,
        )

    return merge


def attach_to_group(group):
    group.add_command(merge_command())
