from logging import ERROR, INFO
from typing import Optional
import click
from logdecorator import log_on_end, log_on_error, log_on_start
from taf.api.utils._roles import setup_role
from taf.messages import git_commit_message
from taf.models.types import RolesIterator
from taf.models.types import RolesKeysData
from taf.api.utils._git import commit_and_push
from taf.models.converter import from_dict

from pathlib import Path
from taf.api.roles import (
    create_delegations,
    _initialize_roles_and_keystore,
)
from taf.api.targets import register_target_files

from taf.auth_repo import AuthenticationRepository
from taf.exceptions import TAFError
from taf.keys import load_sorted_keys_of_new_roles
from tuf.repository_tool import create_new_repository
from taf.log import taf_logger


@log_on_start(
    INFO, "Creating a new authentication repository {path:s}", logger=taf_logger
)
@log_on_end(INFO, "Finished creating a new repository", logger=taf_logger)
@log_on_error(
    ERROR,
    "An error occurred while creating a new repository: {e}",
    logger=taf_logger,
    on_exceptions=TAFError,
    reraise=True,
)
def create_repository(
    path: str,
    keystore: Optional[str] = None,
    roles_key_infos: Optional[str] = None,
    commit: Optional[bool] = False,
    test: Optional[bool] = False,
) -> None:
    """
    Create a new authentication repository. Generate initial metadata files.
    If target files already exist, add corresponding targets information to
    targets metadata files.

    Arguments:
        path: Authentication repository's location.
        keystore: Location of the keystore files.
        roles_key_infos: Path to a json file which contains information about repository's roles and keys.
        commit (optional): Indicates if the changes should be committed and pushed automatically.
        test (optional): Specifies if the created repository is a test authentication repository.

    Side Effects:
        Creates a new authentication repository (initializes a new git repository and generates tuf metadata)

    Returns:
        None
    """
    auth_repo = AuthenticationRepository(path=path)

    if not _check_if_can_create_repository(auth_repo):
        return

    roles_key_infos_dict, keystore = _initialize_roles_and_keystore(
        roles_key_infos, keystore
    )

    keystore_path = Path(keystore)
    if not keystore_path.is_dir():
        keystore_path.mkdir(parents=False)

    roles_keys_data = from_dict(roles_key_infos_dict, RolesKeysData)
    repository = create_new_repository(
        str(auth_repo.path), repository_name=auth_repo.name
    )
    signing_keys, verification_keys = load_sorted_keys_of_new_roles(
        auth_repo=auth_repo,
        roles=roles_keys_data.roles,
        yubikeys_data=roles_keys_data.yubikeys,
        keystore=keystore,
    )
    if signing_keys is None:
        return
    # set threshold and register keys of main roles
    # we cannot do the same for the delegated roles until delegations are created
    for role in RolesIterator(roles_keys_data.roles, include_delegations=False):
        setup_role(
            role,
            repository,
            verification_keys[role.name],
            signing_keys.get(role.name),
        )

    create_delegations(
        roles_keys_data.roles.targets, repository, verification_keys, signing_keys
    )

    # if the repository is a test repository, add a target file called test-auth-repo
    if test:
        test_auth_file = (
            Path(auth_repo.path, auth_repo.targets_path) / auth_repo.TEST_REPO_FLAG_FILE
        )
        test_auth_file.touch()

    # register and sign target files (if any)
    auth_repo._tuf_repository = repository
    updated = register_target_files(
        path,
        keystore,
        roles_key_infos,
        commit=False,
        taf_repo=auth_repo,
        write=True,
        no_commit_warning=True,
    )
    if not updated:
        repository.writeall()

    if commit:
        auth_repo.init_repo()
        commit_msg = git_commit_message("create-repo")
        commit_and_push(auth_repo, push=False, commit_msg=commit_msg)
    else:
        print("\nPlease commit manually.\n")


def _check_if_can_create_repository(auth_repo: AuthenticationRepository) -> bool:
    """
    Check if a new authentication repository can be created at the specified location.
    A repository can be created if there is not directory at the repository's location
    or if it does exists, is not the root of a git repository.

    Arguments:
        auth_repo: Authentication repository.

    Side Effects:
        None

    Returns:
        True if a new authentication repository can be created, False otherwise.
    """
    path = Path(auth_repo.path)
    if path.is_dir():
        # check if there is non-empty metadata directory
        if auth_repo.metadata_path.is_dir() and any(auth_repo.metadata_path.iterdir()):
            if auth_repo.is_git_repository:
                print(
                    f'"{path}" is a git repository containing the metadata directory. Generating new metadata files could make the repository invalid. Aborting.'
                )
                return False
            if not click.confirm(
                f'Metadata directory found inside "{path}". Recreate metadata files?'
            ):
                return False
    return True
