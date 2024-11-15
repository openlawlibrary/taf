from contextlib import contextmanager
from pathlib import Path
from typing import List, Optional, Set

from taf.api.utils._conf import find_keystore
from taf.auth_repo import AuthenticationRepository
from taf.constants import DEFAULT_RSA_SIGNATURE_SCHEME
from taf.exceptions import CommandValidationError, InvalidRepositoryError, TAFError
from taf.git import GitRepository
from taf.keys import load_signers
from taf.log import taf_logger
from taf.messages import git_commit_message


@contextmanager
def manage_repo_and_signers(
    auth_repo: AuthenticationRepository,
    roles: Optional[Set[str]] = None,
    keystore: Optional[str] = None,
    scheme: Optional[str] = DEFAULT_RSA_SIGNATURE_SCHEME,
    prompt_for_keys: Optional[bool] = False,
    load_roles=True,
    load_parents=False,
    load_snapshot_and_timestamp=True,
    commit=True,
    push=True,
    commit_key=None,
    commit_msg=None,
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
                keystore_signers, yubikeys = load_signers(
                    auth_repo,
                    role,
                    loaded_yubikeys=loaded_yubikeys,
                    keystore=keystore_path,
                    scheme=scheme,
                    prompt_for_keys=prompt_for_keys,
                )
                auth_repo.load_signers({role: keystore_signers})
        yield
        if auth_repo.something_to_commit() and commit:
            if not commit_msg and commit_key:
                commit_msg = git_commit_message(commit_key)
            auth_repo.commit_and_push(commit_msg=commit_msg, push=push)
        else:
            taf_logger.log("NOTICE", "\nPlease commit manually\n")

    except CommandValidationError:
        pass
    except Exception as e:
        taf_logger.error(f"An error occurred: {e}")
        if auth_repo.is_git_repository:
            auth_repo.clean_and_reset()
        raise TAFError from e
