from functools import partial
from logging import INFO
import click
from logdecorator import log_on_end, log_on_start

from collections import defaultdict
from pathlib import Path
from taf.api.roles import _create_delegations, _initialize_roles_and_keystore, _role_obj
from taf.api.targets import register_target_files

from taf.auth_repo import AuthenticationRepository
from taf.constants import YUBIKEY_EXPIRATION_DATE
from taf.exceptions import TargetsMetadataUpdateError
from taf.keys import get_key_name, load_sorted_keys_of_new_roles
from taf.repository_tool import Repository, yubikey_signature_provider
from tuf.repository_tool import create_new_repository
from taf.log import taf_logger


@log_on_start(
    INFO, "Creating a new authentication repository {repo_path:s}", logger=taf_logger
)
@log_on_end(INFO, "Finished creating a new repository", logger=taf_logger)
def create_repository(
    repo_path, keystore=None, roles_key_infos=None, commit=False, test=False
):
    """
    Create a new authentication repository. Generate initial metadata files.
    If target files already exist, add corresponding targets information to
    targets metadata files.

    Arguments:
        repo_path: Authentication repository's location.
        keystore: Location of the keystore files.
        roles_key_infos: A dictionary whose keys are role names, while values contain information about the keys.
        commit: Specifies if the changes should be automatically committed.
        test: Specifies if the created repository is a test authentication repository.

    Side Effects:
        Creates a new authentication repository (initializes a new git repository and generates tuf metadata)

    Returns:
        None
    """
    yubikeys = defaultdict(dict)
    auth_repo = AuthenticationRepository(path=repo_path)
    repo_path = Path(repo_path)

    if not _check_if_can_create_repository(auth_repo):
        return

    roles_key_infos, keystore = _initialize_roles_and_keystore(
        roles_key_infos, keystore
    )

    repository = create_new_repository(str(auth_repo.path))
    roles_infos = roles_key_infos.get("roles")
    signing_keys, verification_keys = load_sorted_keys_of_new_roles(
        auth_repo, roles_infos, keystore, yubikeys
    )
    # set threshold and register keys of main roles
    # we cannot do the same for the delegated roles until delegations are created
    for role_name, role_key_info in roles_infos.items():
        threshold = role_key_info.get("threshold", 1)
        is_yubikey = role_key_info.get("yubikey", False)
        _setup_role(
            role_name,
            threshold,
            is_yubikey,
            repository,
            verification_keys[role_name],
            signing_keys.get(role_name),
        )

    _create_delegations(roles_infos, repository, verification_keys, signing_keys)

    # if the repository is a test repository, add a target file called test-auth-repo
    if test:
        test_auth_file = (
            Path(auth_repo.path, auth_repo.targets_path) / auth_repo.TEST_REPO_FLAG_FILE
        )
        test_auth_file.touch()

    # register and sign target files (if any)
    try:
        taf_repository = Repository(repo_path)
        taf_repository._tuf_repository = repository
        register_target_files(
            repo_path,
            keystore,
            roles_key_infos,
            commit=False,
            taf_repo=taf_repository,
            write=True,
        )
    except TargetsMetadataUpdateError:
        # if there are no target files
        repository.writeall()

    if commit:
        auth_repo.init_repo()
        commit_message = input("\nEnter commit message and press ENTER\n\n")
        auth_repo.commit(commit_message)


def _check_if_can_create_repository(auth_repo):
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
    repo_path = Path(auth_repo.path)
    if repo_path.is_dir():
        # check if there is non-empty metadata directory
        if auth_repo.metadata_path.is_dir() and any(auth_repo.metadata_path.iterdir()):
            if auth_repo.is_git_repository:
                print(
                    f'"{repo_path}" is a git repository containing the metadata directory. Generating new metadata files could make the repository invalid. Aborting.'
                )
                return False
            if not click.confirm(
                f'Metadata directory found inside "{repo_path}". Recreate metadata files?'
            ):
                return False
    return True


def _setup_role(
    role_name,
    threshold,
    is_yubikey,
    repository,
    verification_keys,
    signing_keys=None,
    parent=None,
):
    """
    Set up a role, which can either be one of the main TUF roles, or a delegated role.
    Define threshold and signing and verification keys of the role and link it with the repository.

    Arguments:
        role_name: Role's name, either one of the main TUF roles or a delegated role.
        threshold: Signatures threshold.
        is_yubikey: Indicates if the role's metadata file should be signed using Yubikeys or not.
        repository: TUF repository
        verification_keys: Public keys used to verify the signatures
        signing_keys (optional): Signing (private) keys, which only need to be specified if Yubikeys are not used
        parent: The role's parent role

    Side Effects:
        Adds a new role to the TUF repository and sets up its threshold and signing and verification keys

    Returns:
        None
    """
    role_obj = _role_obj(role_name, repository, parent)
    role_obj.threshold = threshold
    if not is_yubikey:
        for public_key, private_key in zip(verification_keys, signing_keys):
            role_obj.add_verification_key(public_key)
            role_obj.load_signing_key(private_key)
    else:
        for key_num, key in enumerate(verification_keys):
            key_name = get_key_name(role_name, key_num, len(verification_keys))
            role_obj.add_verification_key(key, expires=YUBIKEY_EXPIRATION_DATE)
            role_obj.add_external_signature_provider(
                key, partial(yubikey_signature_provider, key_name, key["keyid"])
            )
