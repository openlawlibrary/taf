from taf.tuf.repository import MAIN_ROLES
from logging import DEBUG
from typing import Dict
from logdecorator import log_on_start
from taf import YubikeyMissingLibrary
from taf.auth_repo import AuthenticationRepository
from taf.log import taf_logger


ykman_installed = True
try:
    import taf.yubikey as yk
except ImportError:
    yk = YubikeyMissingLibrary()  # type: ignore


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
