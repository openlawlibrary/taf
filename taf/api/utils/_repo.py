from contextlib import contextmanager
from functools import wraps
from pathlib import Path
from typing import List, Optional, Set

from taf.api.utils._conf import find_keystore
from taf.auth_repo import AuthenticationRepository
from taf.constants import DEFAULT_RSA_SIGNATURE_SCHEME
from taf.exceptions import InvalidRepositoryError
from taf.git import GitRepository
from taf.keys import load_signers
from taf.log import taf_logger


@contextmanager
def manage_repo_and_signers(
    path: str,
    roles: Optional[Set[str]]=None,
    keystore: Optional[str]=None,
    scheme: Optional[str]=DEFAULT_RSA_SIGNATURE_SCHEME,
    prompt_for_keys: Optional[bool]=False,
    roles_fn=None,
    load_roles=True,
    load_parents=False,
    load_snapshot_and_timestamp=True,
):
    try:
        repo = AuthenticationRepository(path=path)
        if not roles and roles_fn:
            roles = roles_fn(repo)
        if roles:
            if not keystore:
                keystore_path = find_keystore(path)
            else:
                keystore_path = Path(keystore)
            loaded_yubikeys = {}
            roles_to_load = set()
            if load_roles:
                roles_to_load.update(roles)
            if load_parents:
                roles_to_load.update(repo.find_parents_of_roles(roles))
            if load_snapshot_and_timestamp:
                roles_to_load.add("snapshot")
                roles_to_load.add("timestamp")

            for role in roles_to_load:
                keystore_signers, yubikeys = load_signers(
                    repo,
                    role,
                    loaded_yubikeys=loaded_yubikeys,
                    keystore=keystore_path,
                    scheme=scheme,
                    prompt_for_keys=prompt_for_keys,
                )
                repo.load_signers({role: keystore_signers})
        yield repo
    except InvalidRepositoryError:
        taf_logger.error("Cannot instantiate repository. This is mostly likely a bug")
        raise
    except Exception:
        repo = GitRepository(path=path)
        if repo.is_git_repository:
            repo.clean_and_reset()
        raise
