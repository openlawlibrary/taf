from contextlib import contextmanager
from pathlib import Path
from typing import List, Optional, Set

from taf.api.utils._conf import find_keystore
from taf.auth_repo import AuthenticationRepository
from taf.constants import DEFAULT_RSA_SIGNATURE_SCHEME
from taf.exceptions import TAFError
from taf.keys import load_signers
from taf.log import taf_logger
from taf.messages import git_commit_message
from taf.constants import METADATA_DIRECTORY_NAME


@contextmanager
def manage_repo_and_signers(
    auth_repo: AuthenticationRepository,
    roles: Optional[Set[str]] = None,
    keystore: Optional[str] = None,
    scheme: Optional[str] = DEFAULT_RSA_SIGNATURE_SCHEME,
    prompt_for_keys: Optional[bool] = False,
    paths_to_reset_on_error: List[str] = None,
    load_roles: bool = True,
    load_parents: bool =False,
    load_snapshot_and_timestamp: bool =True,
    commit: bool =True,
    push: bool =True,
    commit_key: str=None,
    commit_msg: str=None,
    no_commit_warning: bool =True,
):
    try:
        if roles:
            if not keystore:
                keystore_path = find_keystore(auth_repo.path)
            else:
                keystore_path = Path(keystore)
            loaded_yubikeys = {}
            roles_to_load = set()
            if load_roles:
                roles_to_load.update(roles)
            if load_parents:
                roles_to_load.update(auth_repo.find_parents_of_roles(roles))
            if load_snapshot_and_timestamp:
                roles_to_load.add("snapshot")
                roles_to_load.add("timestamp")

                for role in roles_to_load:
                    if not auth_repo.check_if_keys_loaded(role):
                        keystore_signers, yubikeys = load_signers(
                            auth_repo,
                            role,
                            loaded_yubikeys=loaded_yubikeys,
                            keystore=keystore_path,
                            scheme=scheme,
                            prompt_for_keys=prompt_for_keys,
                        )
                        auth_repo.add_signers_to_cache({role: keystore_signers})
        yield
        if auth_repo.something_to_commit() and commit:
            if not commit_msg and commit_key:
                commit_msg = git_commit_message(commit_key)
            auth_repo.commit_and_push(commit_msg=commit_msg, push=push)
        elif not no_commit_warning:
            taf_logger.log("NOTICE", "\nPlease commit manually\n")

    except Exception as e:
        taf_logger.error(f"An error occurred: {e}")
        if not paths_to_reset_on_error:
            paths_to_reset_on_error = [METADATA_DIRECTORY_NAME]
        elif METADATA_DIRECTORY_NAME not in paths_to_reset_on_error:
            paths_to_reset_on_error.append(METADATA_DIRECTORY_NAME)

        if auth_repo.is_git_repository:
            # restore metadata, leave targets as they might have been modified by the user
            # TODO flag for also resetting targets?
            # also update the CLI error handling
            import pdb; pdb.set_trace()
            auth_repo.restore(paths_to_reset_on_error)

        raise TAFError from e
