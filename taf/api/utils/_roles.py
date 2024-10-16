import tuf
from logging import DEBUG, INFO
from typing import Dict, List, Optional, Union
from functools import partial
from logdecorator import log_on_end, log_on_start
from tuf.repository_tool import Repository as TUFRepository, Targets
from taf.exceptions import TAFError
from taf.models.types import RolesIterator
from tuf.repository_tool import Metadata
from taf import YubikeyMissingLibrary
from taf.keys import get_key_name
from taf.auth_repo import AuthenticationRepository
from taf.constants import YUBIKEY_EXPIRATION_DATE
from taf.repository_tool import MAIN_ROLES, Repository, yubikey_signature_provider
from taf.models.types import Role
from taf.log import taf_logger

ykman_installed = True
try:
    import taf.yubikey as yk
except ImportError:
    yk = YubikeyMissingLibrary()  # type: ignore


@log_on_start(INFO, "Creating delegations", logger=taf_logger)
@log_on_end(DEBUG, "Finished creating delegations", logger=taf_logger)
def create_delegations(
    role: Role,
    repository: AuthenticationRepository,
    verification_keys: Dict,
    signing_keys: Dict,
    existing_roles: Optional[List[str]] = None,
) -> None:
    """
    Initialize new delegated target roles, update authentication repository object

    Arguments:
        role: Targets main role or a delegated role
        repository: Authentication repository.
        verification_keys: A dictionary containing mappings of role names to their verification (public) keys.
        signing_keys: A dictionary containing mappings of role names to their signing (private) keys.
        existing_roles: A list of already initialized roles.

    Side Effects:
        Updates authentication repository object

    Returns:
        None
    """
    if existing_roles is None:
        existing_roles = []
    skip_top_role = role.name == "targets"
    try:
        for delegated_role in RolesIterator(role, skip_top_role=skip_top_role):
            parent_role_obj = _role_obj(delegated_role.parent.name, repository)
            if not isinstance(parent_role_obj, Targets):
                raise TAFError(
                    f"Could not find parent targets role of role {delegated_role}"
                )
            if delegated_role.name in existing_roles:
                taf_logger.log("NOTICE", f"Role {delegated_role.name} already set up.")
                continue
            paths = delegated_role.paths
            roles_verification_keys = verification_keys[delegated_role.name]
            # if yubikeys are used for signing, signing keys are not loaded
            roles_signing_keys = signing_keys.get(delegated_role.name)
            parent_role_obj.delegate(
                delegated_role.name,
                roles_verification_keys,
                paths,
                threshold=delegated_role.threshold,
                terminating=delegated_role.terminating,
            )
            setup_role(
                delegated_role,
                repository,
                roles_verification_keys,
                roles_signing_keys,
                parent=parent_role_obj,
            )
    except tuf.exceptions.InvalidNameError:
        raise TAFError("All delegated paths should be relative to targets directory.")


@log_on_start(DEBUG, "Finding roles of key", logger=taf_logger)
def get_roles_and_paths_of_key(
    public_key: Dict,
    repository: AuthenticationRepository,
):
    roles = repository.find_associated_roles_of_key(public_key)
    roles_with_paths: Dict = {role: {} for role in roles}
    for role in roles:
        if role not in MAIN_ROLES:
            roles_with_paths[role] = repository.get_role_paths(role)
    return roles_with_paths


@log_on_start(INFO, "Setting up role {role.name:s}", logger=taf_logger)
@log_on_end(DEBUG, "Finished setting up role {role.name:s}", logger=taf_logger)
def setup_role(
    role: Role,
    repository: TUFRepository,
    verification_keys: Dict,
    signing_keys: Optional[Dict] = None,
    parent: Optional[Targets] = None,
) -> None:
    """
    Initialize a new role, add signing and verification keys.
    """
    role_obj = _role_obj(role.name, repository, parent)
    role_obj.threshold = role.threshold
    if not role.is_yubikey:
        if verification_keys is None or signing_keys is None:
            raise TAFError(f"Cannot setup role {role.name}. Keys not specified")
        for public_key, private_key in zip(verification_keys, signing_keys):
            role_obj.add_verification_key(public_key)
            role_obj.load_signing_key(private_key)
    else:
        yubikeys = role.yubikeys
        if yubikeys is None:
            yubikeys = [
                get_key_name(role.name, count, role.number)
                for count in range(role.number)
            ]
        for key_name, key in zip(yubikeys, verification_keys):
            role_obj.add_verification_key(key, expires=YUBIKEY_EXPIRATION_DATE)
            # check if yubikey loaded
            if yk.get_key_serial_by_id(key_name):
                role_obj.add_external_signature_provider(
                    key, partial(yubikey_signature_provider, key_name, key["keyid"])
                )
        # Even though we add all verification keys (public keys directly specified in the keys-description)
        # and those loaded from YubiKeys, only those directly specified in keys-description are registered
        # as previous_keys
        # this means that TUF expects at least one of those signing keys to be present
        # we are setting up this role, so there should be no previous keys

        try:
            tuf.roledb._roledb_dict[repository._repository_name][role.name][
                "previous_keyids"
            ] = []
        except Exception:  # temporary quick fix, this will all be reworked
            tuf.roledb._roledb_dict[repository.name][role.name]["previous_keyids"] = []


def _role_obj(
    role: str,
    repository: Union[Repository, TUFRepository],
    parent: Optional[Targets] = None,
) -> Metadata:
    """
    Return role TUF object based on its name
    """
    if isinstance(repository, Repository):
        tuf_repository = repository._repository
    else:
        tuf_repository = repository
    if role == "targets":
        return tuf_repository.targets
    elif role == "snapshot":
        return tuf_repository.snapshot
    elif role == "timestamp":
        return tuf_repository.timestamp
    elif role == "root":
        return tuf_repository.root
    else:
        # return delegated role
        if parent is None:
            return tuf_repository.targets(role)
        return parent(role)


def list_roles(repository: AuthenticationRepository) -> List[str]:
    """
    Return a list of all defined roles, main roles combined with delegated targets roles.
    """
    return repository.get_all_roles()
