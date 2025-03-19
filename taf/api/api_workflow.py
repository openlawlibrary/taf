from contextlib import contextmanager
import functools
from pathlib import Path
from typing import Callable, Dict, List, Optional, Union

from taf.api.utils._conf import find_keystore, read_keys_name_mapping
from taf.api.yubikey import get_yk_roles
from taf.auth_repo import AuthenticationRepository
from taf.constants import DEFAULT_RSA_SIGNATURE_SCHEME
from taf.exceptions import PushFailedError, TAFError
from taf.keys import load_signers
from taf.messages import git_commit_message
from taf.constants import METADATA_DIRECTORY_NAME
from taf.log import taf_logger
from taf.utils import read_extra_args
from taf.yubikey.yubikey_manager import manage_pins


def key_management(
    roles: Optional[List[str]] = None,
    roles_fn: Optional[Callable[[Dict[str, str]], List[str]]] = None,
) -> Callable:
    """
    Decorator that:
    - Captures dynamic PIN arguments
    - Ensures necessary signers are loaded.
    - Cleans up PIN manager
    - Reads key name mappings if `keys_description` is provided.

    Parameters:
    - path (str): Path to the authentication repository.
    - roles (Optional[List[str]]): List of predefined roles to be loaded.
    - roles_fn (Optional[Callable[[Dict[str, str]], List[str]]]): Function that determines roles to be loaded.
    - keystore_path (Optional[str]): Path to the keystore.
    - keys_description (Optional[str]): Path to a key description file.

    Returns:
    - Callable: Decorated function with authentication management.
    """
    roles = roles or []

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            path: Path = kwargs.pop("path")
            auth_repo = AuthenticationRepository(path=path)

            keystore_path = kwargs.get("keystore")
            keys_description = kwargs.get("keys_description")

            if keys_description:
                keys_name_mappings = read_keys_name_mapping(keys_description)
                auth_repo.add_key_names(keys_name_mappings)

            all_roles = list(roles)
            if callable(roles_fn):
                roles_to_update = roles_fn()
                if isinstance(roles_to_update, list):
                    all_roles.extend(roles_to_update)
                else:
                    taf_logger.error("roles_fn must return a list")
                    raise TAFError("roles_fn must return a list")

            all_roles = list(set(all_roles))
            if not all_roles:
                # determine roles based on the inserted yubikeys
                roles_per_yks = get_yk_roles(path)
                for yk_roles in roles_per_yks.values():
                    for role in yk_roles:
                        if role not in all_roles:
                            all_roles.append(role)

            if not all_roles:
                taf_logger.error("No roles specified")
                raise TAFError("No roles specified")

            taf_logger.info(f"Loading keys of roles {', '.join(all_roles)}")

            with manage_pins() as pin_manager:

                auth_repo.pin_manager = pin_manager
                pin_args: Dict[str, str] = read_extra_args(kwargs, "pin")
                key_id_pins = _map_keynames_to_keyids(auth_repo, pin_args)

                # Load signers for required roles
                for role in all_roles:
                    if not auth_repo.check_if_keys_loaded(role):
                        keystore_signers, yubikey_signers = load_signers(
                            auth_repo,
                            role,
                            keystore=keystore_path,
                            key_id_pins=key_id_pins,
                        )
                        auth_repo.add_signers_to_cache({role: keystore_signers})
                        auth_repo.add_signers_to_cache({role: yubikey_signers})

            return func(auth_repo, *args, **kwargs)

        return wrapper

    return decorator


def _map_keynames_to_keyids(
    auth_repo: AuthenticationRepository, pin_args: Dict
) -> Dict:
    """
    Finds key ids based on key names and inserts
    key id and key pin, if specified via pin_args,
    into a dictionary.
    """
    key_id_pins: Dict = {}
    if not pin_args:
        return key_id_pins

    key_name_key_ids = auth_repo.get_key_ids_of_key_names(pin_args.keys())
    for key_name, key_id in key_name_key_ids.items():
        if key_name in pin_args:
            key_id_pins[key_id] = pin_args[key_name]

    if len(key_id_pins) != len(pin_args):
        all_roles = auth_repo.get_all_roles()
        for key_name, key_pin in pin_args.items():
            for role_name in all_roles:
                if role_name == key_name:
                    key_ids = auth_repo.get_key_ids_of_role(role_name)
                    if len(key_ids) == 1:
                        key_id_pins[key_ids[0]] = key_pin

    if len(key_id_pins) != len(pin_args):
        not_existing_names = [
            key_name for key_name in pin_args if key_name not in key_id_pins
        ]
        taf_logger.error(f"Keys {', '.join(not_existing_names)} not defined")
        raise TAFError(f"Keys {', '.join(not_existing_names)} not defined")
    return key_id_pins


@contextmanager
def transactional_execution(auth_repo):
    initial_commit = auth_repo.head_commit()
    try:
        yield
    except PushFailedError:
        pass
    except Exception:
        auth_repo.reset_to_commit(initial_commit, hard=True)
        raise


@contextmanager
def manage_repo_and_signers(
    auth_repo: AuthenticationRepository,
    roles: Optional[List[str]] = None,
    keystore: Optional[Union[str, Path]] = None,
    scheme: Optional[str] = DEFAULT_RSA_SIGNATURE_SCHEME,
    prompt_for_keys: Optional[bool] = False,
    paths_to_reset_on_error: Optional[List[Union[str, Path]]] = None,
    load_roles: Optional[bool] = True,
    load_parents: Optional[bool] = False,
    load_snapshot_and_timestamp: Optional[bool] = True,
    commit: Optional[bool] = True,
    push: Optional[bool] = True,
    commit_key: Optional[str] = None,
    commit_msg: Optional[str] = None,
    no_commit_warning: Optional[bool] = True,
):
    """
    A context manager that loads all signers and adds them to the specified authentication repository's
    signers cache. This allows for the execution of other methods without having to update the
    signers cache manually. Optionally, at the end, the context manager commits and pushes all changes made
    to the authentication repository and handles cleanup in case of an error.

    Arguments:
        auth_repo (AuthenticationRepository): Already instantiated authentication repository.
        roles (Optional[List[str]]): List of roles that are expected to be updated.
        keystore (Optional[Union[str, Path]]): Path to the keystore containing signing keys.
        scheme (Optional[str]): The signature scheme.
        prompt_for_keys (Optional[bool]): If True, prompts for keys if not found. Defaults to False.
        paths_to_reset_on_error (Optional[List[Union[str, Path]]]): Paths to reset if an error occurs.
        load_roles (Optional[bool]): If True, loads signing keys of the roles specified using the argument of the same name.
        load_parents (Optional[bool]): If true, loads sining keys of the specified roles' parents.
        load_snapshot_and_timestamp (Optional[bool]): If True, loads snapshot and timestamp signing keys.
        commit (Optional[bool]): If True, commits changes to the repository.
        push (Optional[bool]): If True, pushes changes to the remote repository.
        commit_key (Optional[str]): Commit key from `messages.py`
        commit_msg (Optional[str]): The message to use for commits.
        no_commit_warning (Optional[bool]): If True, suppresses warnings when not committing.
    """
    try:
        roles_to_load = set()
        if roles:
            unique_roles = set(roles)
            if load_roles:
                roles_to_load.update(unique_roles)
            if load_parents:
                roles_to_load.update(auth_repo.find_parents_of_roles(unique_roles))
        if load_snapshot_and_timestamp:
            roles_to_load.add("snapshot")
            roles_to_load.add("timestamp")
        if roles_to_load:
            if not keystore:
                keystore_path = find_keystore(auth_repo.path)
            else:
                keystore_path = Path(keystore)
            sorted_roles_to_load = sorted(roles_to_load, key=role_priority)
            for role in sorted_roles_to_load:
                if not auth_repo.check_if_keys_loaded(role):
                    keystore_signers, yubikey_signers = load_signers(
                        auth_repo,
                        role,
                        keystore=keystore_path,
                        scheme=scheme,
                        prompt_for_keys=prompt_for_keys,
                    )
                    auth_repo.add_signers_to_cache({role: keystore_signers})
                    auth_repo.add_signers_to_cache({role: yubikey_signers})
        yield
        if commit and auth_repo.something_to_commit():
            if not commit_msg and commit_key:
                commit_msg = git_commit_message(commit_key)
            auth_repo.commit_and_push(commit_msg=commit_msg, push=push)
        elif not no_commit_warning:
            taf_logger.log("NOTICE", "\nPlease commit manually\n")

    except PushFailedError as e:
        taf_logger.error(e)
        raise
    except Exception as e:
        taf_logger.error(f"An error occurred: {e}")
        if not paths_to_reset_on_error:
            paths_to_reset_on_error = [METADATA_DIRECTORY_NAME]
        elif METADATA_DIRECTORY_NAME not in paths_to_reset_on_error:
            paths_to_reset_on_error.append(METADATA_DIRECTORY_NAME)

        if auth_repo.is_git_repository and paths_to_reset_on_error:
            # restore metadata, leave targets as they might have been modified by the user
            # TODO flag for also resetting targets?
            # also update the CLI error handling]
            auth_repo.restore([str(path) for path in paths_to_reset_on_error])

        raise TAFError from e


def role_priority(role):
    """
    Return a numeric priority for the given role. This can be used as a sort order key.
    Example: sorted(roles, key=role_priority)

    The order is:
    0. root
    1. targets
    2. (delegated roles)
    3. snapshot
    4. timestamp

    Anything not explicitly listed is considered a "delegated role."
    """
    if role == "root":
        return 0
    elif role == "targets":
        return 1
    elif role == "snapshot":
        return 3
    elif role == "timestamp":
        return 4
    else:
        return 2
