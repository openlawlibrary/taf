from contextlib import contextmanager
from pathlib import Path
from typing import Dict, List, Optional, Union

from taf.api.utils._conf import find_keystore
from taf.auth_repo import AuthenticationRepository
from taf.constants import DEFAULT_RSA_SIGNATURE_SCHEME
from taf.exceptions import PushFailedError, TAFError
from taf.keys import load_signers
from taf.log import taf_logger
from taf.messages import git_commit_message
from taf.constants import METADATA_DIRECTORY_NAME


@contextmanager
def transactional_execution(auth_repo):
    initial_commit = auth_repo.head_commit_sha()
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
            loaded_yubikeys: Dict = {}
            for role in roles_to_load:
                if not auth_repo.check_if_keys_loaded(role):
                    keystore_signers, yubikey_signers = load_signers(
                        auth_repo,
                        role,
                        loaded_yubikeys=loaded_yubikeys,
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

    except PushFailedError:
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
