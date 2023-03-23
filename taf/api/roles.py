from collections import defaultdict
from functools import partial
from pathlib import Path
from taf.api.keys import get_key_name, load_signing_keys, load_sorted_keys_of_roles
from taf.api.metadata import update_snapshot_and_timestamp
from taf.auth_repo import AuthenticationRepository
from taf.constants import YUBIKEY_EXPIRATION_DATE, DEFAULT_RSA_SIGNATURE_SCHEME
from taf.repository_tool import yubikey_signature_provider


def add_role(
    auth_path: str,
    role: str,
    parent_role: str,
    paths: list,
    keys_number: int,
    threshold: int,
    yubikey: bool,
    keystore: str,
    scheme: str,
    auth_repo: AuthenticationRepository=None,
    commit=True,
):

    yubikeys = defaultdict(dict)
    if auth_repo is None:
        auth_repo = AuthenticationRepository(path=auth_path)
    auth_path = Path(auth_path)
    existing_roles = auth_repo.get_all_targets_roles()
    main_roles = ["root", "snapshot", "timestamp", "targets"]
    existing_roles.extend(main_roles)
    if role in existing_roles:
        print("All roles already set up")
        return

    roles_infos = {
        parent_role: {
            "delegations": {
                "roles": {
                    role: {
                        "paths": paths,
                        "number": keys_number,
                        "threshold": threshold,
                        "yubikey": yubikey,
                    }
                }
            }
        }
    }

    signing_keys, verification_keys = load_sorted_keys_of_roles(
        auth_repo, roles_infos, auth_repo, keystore, yubikeys, existing_roles
    )
    _create_delegations(
        roles_infos, auth_repo, verification_keys, signing_keys, existing_roles
    )
    _update_role(auth_repo, parent_role, keystore, roles_infos, scheme=scheme)
    if commit:
        update_snapshot_and_timestamp(auth_repo, keystore, roles_infos, scheme=scheme)
        commit_message = input("\nEnter commit message and press ENTER\n\n")
        auth_repo.commit(commit_message)


def add_role_paths(paths, delegated_role, keystore, commit=True, auth_repo=None, auth_path=None):
    if auth_repo is None:
        auth_repo = AuthenticationRepository(path=auth_path)
    parent_role = auth_repo.find_delegated_roles_parent(delegated_role)
    parent_role_obj = _role_obj(parent_role, auth_repo)
    parent_role_obj.add_paths(paths, delegated_role)
    _update_role(auth_repo, parent_role, keystore)
    if commit:
        update_snapshot_and_timestamp(auth_repo, keystore, None, None)
        commit_message = input("\nEnter commit message and press ENTER\n\n")
        auth_repo.commit(commit_message)


def _create_delegations(
    roles_infos, repository, verification_keys, signing_keys, existing_roles=None
):
    if existing_roles is None:
        existing_roles = []
    for role_name, role_info in roles_infos.items():
        if "delegations" in role_info:
            parent_role_obj = _role_obj(role_name, repository)
            delegations_info = role_info["delegations"]["roles"]
            for delegated_role_name, delegated_role_info in delegations_info.items():
                if delegated_role_name in existing_roles:
                    print(f"Role {delegated_role_name} already set up.")
                    continue
                paths = delegated_role_info.get("paths", [])
                roles_verification_keys = verification_keys[delegated_role_name]
                # if yubikeys are used for signing, signing keys are not loaded
                roles_signing_keys = signing_keys.get(delegated_role_name)
                threshold = delegated_role_info.get("threshold", 1)
                terminating = delegated_role_info.get("terminating", False)
                parent_role_obj.delegate(
                    delegated_role_name,
                    roles_verification_keys,
                    paths,
                    threshold=threshold,
                    terminating=terminating,
                )
                is_yubikey = delegated_role_info.get("yubikey", False)
                _setup_role(
                    delegated_role_name,
                    threshold,
                    is_yubikey,
                    repository,
                    roles_verification_keys,
                    roles_signing_keys,
                    parent=parent_role_obj,
                )
                print(f"Setting up delegated role {delegated_role_name}")
            _create_delegations(
                delegations_info, repository, verification_keys, signing_keys
            )


def _role_obj(role, repository, parent=None):
    repository = repository._tuf_repository
    if role == "targets":
        return repository.targets
    elif role == "snapshot":
        return repository.snapshot
    elif role == "timestamp":
        return repository.timestamp
    elif role == "root":
        return repository.root
    else:
        # return delegated role
        if parent is None:
            return repository.targets(role)
        return parent(role)


def _setup_role(
    role_name,
    threshold,
    is_yubikey,
    repository,
    verification_keys,
    signing_keys=None,
    parent=None,
):
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


def _update_role(taf_repo, role, keystore, roles_infos=None, scheme=DEFAULT_RSA_SIGNATURE_SCHEME):
    keystore_keys, yubikeys = load_signing_keys(
        taf_repo, role, keystore, roles_infos, scheme=scheme
    )
    if len(keystore_keys):
        taf_repo.update_role_keystores(role, keystore_keys, write=False)
    if len(yubikeys):
        taf_repo.update_role_yubikeys(role, yubikeys, write=False)
