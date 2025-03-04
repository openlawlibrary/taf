import json
from logging import ERROR, INFO
import shutil
from typing import Optional
import click
from logdecorator import log_on_end, log_on_error, log_on_start
from taf.git import GitRepository
from taf.messages import git_commit_message
from taf.models.types import RolesKeysData
from taf.models.converter import from_dict

from pathlib import Path
from taf.api.roles import (
    initialize_roles_and_keystore,
)
from taf.api.targets import list_targets, register_target_files

from taf.auth_repo import AuthenticationRepository
from taf.exceptions import TAFError
from taf.keys import load_sorted_keys_of_new_roles
import taf.repositoriesdb as repositoriesdb
from taf.api.utils._conf import find_keystore
from taf.tuf.repository import METADATA_DIRECTORY_NAME
from taf.utils import ensure_pre_push_hook
from taf.log import taf_logger
from taf.yubikey.yubikey_manager import PinManager


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
    pin_manager: PinManager,
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
    if not _check_if_can_create_repository(Path(path)):
        return

    if not keystore and path is not None:
        keystore_path = find_keystore(path)
        if keystore_path is not None:
            keystore = str(keystore_path)
    roles_key_infos_dict, keystore, skip_prompt = initialize_roles_and_keystore(
        roles_key_infos, keystore
    )

    roles_keys_data = from_dict(roles_key_infos_dict, RolesKeysData)
    auth_repo = AuthenticationRepository(path=path, pin_manager=pin_manager)
    signers, verification_keys = load_sorted_keys_of_new_roles(
        roles=roles_keys_data.roles,
        auth_repo=auth_repo,
        yubikeys_data=roles_keys_data.yubikeys,
        keystore=keystore,
        skip_prompt=skip_prompt,
        certs_dir=auth_repo.certs_dir,
    )
    if signers is None:
        return

    auth_repo.create(roles_keys_data, signers, verification_keys)
    if commit:
        auth_repo.init_repo()
        commit_msg = git_commit_message("create-repo")
        auth_repo.commit(commit_msg, ["metadata"])

    if test:
        auth_repo.targets_path.mkdir(exist_ok=True)
        test_auth_file = auth_repo.targets_path / auth_repo.TEST_REPO_FLAG_FILE
        test_auth_file.touch()

    register_target_files(
        path,
        keystore,
        roles_key_infos,
        commit=commit,
        auth_repo=auth_repo,
        update_snapshot_and_timestamp=True,
        no_commit_warning=True,
    )

    ensure_pre_push_hook(auth_repo.path)

    if not commit:
        print("\nPlease commit manually.\n")


def _check_if_can_create_repository(path: Path) -> bool:
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
    repo = GitRepository(path=path)
    if path.is_dir():
        # check if there is non-empty metadata directory
        metadata_dir = path / METADATA_DIRECTORY_NAME
        if metadata_dir.is_dir() and any(metadata_dir.iterdir()):
            if repo.is_git_repository:
                print(
                    f'"{path}" is a git repository containing the metadata directory. Generating new metadata files could make the repository invalid. Aborting.'
                )
                return False
            if not click.confirm(
                f'Metadata directory found inside "{path}". Recreate metadata files?'
            ):
                return False
            else:
                shutil.rmtree(metadata_dir)
    return True


def taf_status(path: str, library_dir: Optional[str] = None, indent: int = 0) -> None:
    """
    Prints a list of target repositories of an authentication repository, their states,
    and the dependencies of the authentication repository.

    Arguments:
        path: Authentication repository's location
        library_dir (optional): Path to the library's root directory. Determined based on the authentication repository's path if not provided.
        indent (optional): Indentation level for nested dependencies.

    Side Effects:
       None

    Returns:
        None
    """
    # Get the authentication repository status
    print()
    auth_repo = AuthenticationRepository(path=path)
    head_commit = auth_repo.head_commit()
    if head_commit is None:
        print("Repository is empty")
        return

    # Print authentication repository status
    indent_str = " " * indent
    print(f"{indent_str}Authentication Repository: {auth_repo.path.resolve()}")
    print(f"{indent_str}Head Commit: {head_commit}")
    print(f"{indent_str}Bare: {auth_repo.is_bare_repository}")
    print(f"{indent_str}Up to Date: {auth_repo.synced_with_remote()}")
    print(f"{indent_str}Something to commit: {auth_repo.something_to_commit()}")
    print(f"{indent_str}Target Repositories Status:")
    # Call the list_targets function
    print(json.dumps(list_targets(path=path), indent=1))

    # Load dependencies using repositoriesdb.get_auth_repositories
    repositoriesdb.load_dependencies(auth_repo, library_dir=library_dir)
    dependencies = repositoriesdb.get_auth_repositories(auth_repo, head_commit)
    if dependencies:
        print(f"{indent_str}Dependencies:")
        for dep_repo in dependencies.values():
            print(f"{indent_str}- {dep_repo.name}")
            taf_status(str(dep_repo.path), library_dir, indent + 3)
