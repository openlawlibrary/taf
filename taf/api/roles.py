import os
import click
from collections import defaultdict
from functools import partial
import json
from pathlib import Path
from taf.hosts import REPOSITORIES_JSON_PATH
from tuf.repository_tool import TARGETS_DIRECTORY_NAME
import tuf.roledb
import taf.repositoriesdb as repositoriesdb
from taf.keys import get_key_name, load_signing_keys, load_sorted_keys_of_roles
from taf.api.metadata import update_snapshot_and_timestamp, update_target_metadata
from taf.auth_repo import AuthenticationRepository
from taf.constants import (
    DEFAULT_ROLE_SETUP_PARAMS,
    YUBIKEY_EXPIRATION_DATE,
    DEFAULT_RSA_SIGNATURE_SCHEME,
)
from taf.keystore import _default_keystore_path, new_public_key_cmd_prompt
from taf.repository_tool import (
    Repository,
    is_delegated_role,
    yubikey_signature_provider,
)
from taf.utils import get_key_size, read_input_dict


MAIN_ROLES = ["root", "snapshot", "timestamp", "targets"]


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
    auth_repo: AuthenticationRepository = None,
    commit=True,
):

    yubikeys = defaultdict(dict)
    if auth_repo is None:
        auth_repo = AuthenticationRepository(path=auth_path)
    auth_path = Path(auth_path)
    existing_roles = auth_repo.get_all_targets_roles()
    existing_roles.extend(MAIN_ROLES)
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


def add_role_paths(
    paths, delegated_role, keystore, commit=True, auth_repo=None, auth_path=None
):
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


def add_signing_key(
    repo_path,
    roles,
    pub_key_path=None,
    keystore=None,
    roles_key_infos=None,
    scheme=DEFAULT_RSA_SIGNATURE_SCHEME,
):
    """
    Adds a new signing key to the listed roles. Automatically updates timestamp and
    snapshot.
    """
    taf_repo = Repository(repo_path)
    roles_key_infos, keystore = _initialize_roles_and_keystore(
        roles_key_infos, keystore, enter_info=False
    )
    roles_infos = roles_key_infos.get("roles")

    pub_key_pem = None
    if pub_key_path is not None:
        pub_key_path = Path(pub_key_path)
        if pub_key_path.is_file():
            pub_key_pem = Path(pub_key_path).read_text()

    if pub_key_pem is None:
        pub_key_pem = new_public_key_cmd_prompt(scheme)["keyval"]["public"]

    parent_roles = set()
    for role in roles:
        if taf_repo.is_valid_metadata_key(role, pub_key_pem):
            print(f"Key already registered as signing key of role {role}")
            continue

        taf_repo.add_metadata_key(role, pub_key_pem, scheme)

        if is_delegated_role(role):
            parent_role = taf_repo.find_delegated_roles_parent(role)
        else:
            parent_role = "root"

        parent_roles.add(parent_role)

    if not len(parent_roles):
        return

    taf_repo.unmark_dirty_roles(list(set(roles) - parent_roles))
    for parent_role in parent_roles:
        _update_role(taf_repo, parent_role, keystore, roles_infos, scheme)

    update_snapshot_and_timestamp(taf_repo, keystore, roles_infos, scheme=scheme)


def _enter_roles_infos(keystore, roles_key_infos):
    """
    Ask the user to enter information taf roles and keys, including the location
    of keystore directory if not entered through an input parameter
    """
    mandatory_roles = ["root", "targets", "snapshot", "timestamp"]
    role_key_infos = defaultdict(dict)
    infos_json = {}

    for role in mandatory_roles:
        role_key_infos[role] = _enter_role_info(role, role == "targets", keystore)
    infos_json["roles"] = role_key_infos

    while keystore is None:
        keystore = input(
            "Enter keystore location if keys should be loaded from or generated to keystore files (leave empty otherwise): "
        )
        if len(keystore):
            if not Path(keystore).is_dir():
                print(f"{keystore} does not exist")
                keystore = None

    if keystore:
        infos_json["keystore"] = keystore

    def _print_roles_key_infos(infos_json_str):
        print("------------------")
        print(
            "Configuration json - save it in order to make creation of repositories quicker"
        )
        print(json.dumps(infos_json, indent=4))
        print("------------------")

    infos_json_str = json.dumps(infos_json, indent=4)
    if isinstance(roles_key_infos, str):
        try:
            path = Path(roles_key_infos)
            path.parent.mkdir(parents=True, exist_ok=True)
            Path(roles_key_infos).write_text(infos_json_str)
            print(f"Configuration json written to {Path(roles_key_infos).absolute()}")
        except Exception as e:
            print(e)
            _print_roles_key_infos(infos_json_str)
    else:
        print(infos_json_str)
    return infos_json


def _enter_role_info(role, is_targets_role, keystore):
    def _read_val(input_type, name, param=None, required=False):
        default_value_msg = ""
        if param is not None:
            default = DEFAULT_ROLE_SETUP_PARAMS.get(param)
            if default is not None:
                default_value_msg = f"(default {DEFAULT_ROLE_SETUP_PARAMS[param]}) "

        while True:
            try:
                val = input(f"Enter {name} and press ENTER {default_value_msg}")
                if not val:
                    if not required:
                        return DEFAULT_ROLE_SETUP_PARAMS.get(param)
                    else:
                        continue
                return input_type(val)
            except ValueError:
                pass

    role_info = {}
    keys_num = _read_val(int, f"number of {role} keys", "number")
    if keys_num is not None:
        role_info["number"] = keys_num

    role_info["yubikey"] = click.confirm(f"Store {role} keys on Yubikeys?")
    if role_info["yubikey"]:
        # in case of yubikeys, length and shceme have to have specific values
        role_info["length"] = 2048
        role_info["scheme"] = DEFAULT_RSA_SIGNATURE_SCHEME
    else:
        # if keystore is specified and contain keys corresponding to this role
        # get key size based on the public key
        keystore_length = _get_roles_key_size(role, keystore, keys_num)
        if keystore_length == 0:
            key_length = _read_val(int, f"{role} key length", "length")
            if key_length is not None:
                role_info["length"] = key_length
        else:
            role_info["length"] = keystore_length
        scheme = _read_val(str, f"{role} signature scheme", "scheme")
        if scheme is not None:
            role_info["scheme"] = scheme

    threshold = _read_val(int, f"{role} signature threshold", "threshold")
    if threshold is not None:
        role_info["threshold"] = threshold

    if is_targets_role:
        delegated_roles = defaultdict(dict)
        while click.confirm(
            f"Add {'another' if len(delegated_roles) else 'a'} delegated targets role of role {role}?"
        ):
            role_name = _read_val(str, "role name", True)
            delegated_paths = []
            while not len(delegated_paths) or click.confirm("Enter another path?"):
                delegated_paths.append(
                    _read_val(
                        str, f"path or glob pattern delegated to {role_name}", True
                    )
                )
            delegated_roles[role_name]["paths"] = delegated_paths
            is_terminating = click.confirm(f"Is {role_name} terminating?")
            delegated_roles[role_name]["terminating"] = is_terminating
            delegated_roles[role_name].update(
                _enter_role_info(role_name, True, keystore)
            )
        role_info["delegations"] = delegated_roles

    return role_info


def _initialize_roles_and_keystore(roles_key_infos, keystore, enter_info=True):
    """
    Read or enter roles information and try to extract keystore path from
    that json
    """
    roles_key_infos_dict = read_input_dict(roles_key_infos)
    if keystore is None:
        keystore = roles_key_infos_dict.get("keystore") or _default_keystore_path()

    if enter_info and not len(roles_key_infos_dict):
        # ask the user to enter roles, number of keys etc.
        roles_key_infos_dict = _enter_roles_infos(keystore, roles_key_infos)

    return roles_key_infos_dict, keystore


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


def _get_roles_key_size(role, keystore, keys_num):
    pub_key_name = f"{get_key_name(role, 1, keys_num)}.pub"
    key_path = str(Path(keystore, pub_key_name))
    return get_key_size(key_path)


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


def remove_role(
    auth_path: str,
    role: str,
    keystore: str,
    scheme: str = DEFAULT_RSA_SIGNATURE_SCHEME,
    commit: bool = True,
    remove_targets: bool = False,
    auth_repo: AuthenticationRepository = None,
):
    if role in MAIN_ROLES:
        print(
            f"Cannot remove role {role}. It is one of the roles required by the TUF specification"
        )
        return

    if auth_repo is None:
        auth_repo = AuthenticationRepository(path=auth_path)

    parent_role = auth_repo.find_delegated_roles_parent(role)
    if parent_role is None:
        print("Role is not among delegated roles")
        return

    roleinfo = tuf.roledb.get_roleinfo(parent_role, auth_repo.name)
    added_targets_data = {}
    removed_targets = []
    for delegations_data in roleinfo["delegations"]["roles"]:
        if delegations_data["name"] == role:
            paths = delegations_data["paths"]
            for path in paths:
                target_file_path = Path(auth_path, TARGETS_DIRECTORY_NAME, path)
                if target_file_path.is_file():
                    if remove_targets:
                        os.unlink(str(target_file_path))
                        removed_targets.append(path)
                    else:
                        added_targets_data[path] = {}
            break

    parent_role_obj = _role_obj(parent_role, auth_repo)
    parent_role_obj.revoke(role)

    _update_role(auth_repo, parent_role, keystore)
    if len(added_targets_data):
        removed_targets_data = {}
        update_target_metadata(
            auth_repo,
            added_targets_data,
            removed_targets_data,
            keystore,
            roles_infos=None,
            write=False,
            scheme=DEFAULT_RSA_SIGNATURE_SCHEME,
        )

    # if targets should be deleted, also removed them from repositories.json
    if len(removed_targets):
        repositories_json = repositoriesdb.load_repositories_json(auth_repo)
        repositories = repositories_json["repositories"]
        for removed_target in removed_targets:
            if removed_target in repositories:
                repositories.pop(removed_target)

            # update content of repositories.json before updating targets metadata
            Path(auth_repo.path, REPOSITORIES_JSON_PATH).write_text(
                json.dumps(repositories_json, indent=4)
            )

    update_snapshot_and_timestamp(auth_repo, keystore, None, scheme)
    if commit:
        commit_message = input("\nEnter commit message and press ENTER\n\n")
        auth_repo.commit(commit_message)


def remove_paths(paths, keystore, commit=True, auth_repo=None, auth_path=None):
    if auth_repo is None:
        auth_repo = AuthenticationRepository(path=auth_path)
    for path in paths:
        delegated_role = auth_repo.get_role_from_target_paths([path])
        if delegated_role != "targets":
            parent_role = auth_repo.find_delegated_roles_parent(delegated_role)
            # parent_role_obj = _role_obj(parent_role, auth_repo)
            _remove_path_from_role_info(path, parent_role, delegated_role, auth_repo)
            _update_role(auth_repo, parent_role, keystore)
    if commit:
        update_snapshot_and_timestamp(auth_repo, keystore, None, None)
        commit_message = input("\nEnter commit message and press ENTER\n\n")
        auth_repo.commit(commit_message)


def _remove_path_from_role_info(path, parent_role, delegated_role, auth_repo):
    # Update the role's 'roledb' entry and avoid duplicates.
    auth_repo.reload_tuf_repository()
    roleinfo = tuf.roledb.get_roleinfo(parent_role, auth_repo.name)
    for delegations_data in roleinfo["delegations"]["roles"]:
        if delegations_data["name"] == delegated_role:
            delegations_paths = delegations_data["paths"]
            if path in delegations_paths:
                delegations_paths.remove(path)
            else:
                print(f"{path} not in delegated paths")
            break
    tuf.roledb.update_roleinfo(parent_role, roleinfo, repository_name=auth_repo.name)


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


def _update_role(
    taf_repo, role, keystore, roles_infos=None, scheme=DEFAULT_RSA_SIGNATURE_SCHEME
):
    keystore_keys, yubikeys = load_signing_keys(
        taf_repo, role, keystore, roles_infos, scheme=scheme
    )
    if len(keystore_keys):
        taf_repo.update_role_keystores(role, keystore_keys, write=False)
    if len(yubikeys):
        taf_repo.update_role_yubikeys(role, yubikeys, write=False)
