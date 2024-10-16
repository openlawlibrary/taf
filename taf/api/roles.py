import glob
from logging import DEBUG, ERROR
import os
from typing import Dict, List, Optional, Tuple
import click
from collections import defaultdict
import json
from pathlib import Path
from logdecorator import log_on_end, log_on_error, log_on_start
from taf.api.utils._roles import _role_obj, create_delegations
from taf.messages import git_commit_message
from tuf.repository_tool import Targets
from taf.api.utils._git import check_if_clean, commit_and_push
from taf.exceptions import KeystoreError, TAFError
from taf.models.converter import from_dict
from taf.models.types import RolesIterator, TargetsRole, compare_roles_data
from taf.repositoriesdb import REPOSITORIES_JSON_PATH
from tuf.repository_tool import TARGETS_DIRECTORY_NAME
import tuf.roledb
import taf.repositoriesdb as repositoriesdb
from taf.keys import (
    find_keystore,
    get_key_name,
    get_metadata_key_info,
    load_signing_keys,
    load_sorted_keys_of_new_roles,
)
from taf.api.utils._metadata import (
    update_snapshot_and_timestamp,
    update_target_metadata,
)
from taf.auth_repo import AuthenticationRepository
from taf.constants import (
    DEFAULT_ROLE_SETUP_PARAMS,
    DEFAULT_RSA_SIGNATURE_SCHEME,
)
from taf.keystore import new_public_key_cmd_prompt
from taf.repository_tool import is_delegated_role
from taf.utils import get_key_size, read_input_dict, resolve_keystore_path
from taf.log import taf_logger
from taf.models.types import RolesKeysData


MAIN_ROLES = ["root", "snapshot", "timestamp", "targets"]


@log_on_start(DEBUG, "Adding a new role {role:s}", logger=taf_logger)
@log_on_end(DEBUG, "Finished adding a new role", logger=taf_logger)
@log_on_error(
    ERROR,
    "An error occurred while adding a new role {role:s}: {e}",
    logger=taf_logger,
    on_exceptions=TAFError,
    reraise=True,
)
@check_if_clean
def add_role(
    path: str,
    role: str,
    parent_role: str,
    paths: list,
    keys_number: int,
    threshold: int,
    yubikey: bool,
    keystore: str,
    scheme: Optional[str] = DEFAULT_RSA_SIGNATURE_SCHEME,
    auth_repo: Optional[AuthenticationRepository] = None,
    commit: Optional[bool] = True,
    prompt_for_keys: Optional[bool] = False,
    push: Optional[bool] = True,
    skip_prompt: Optional[bool] = False,
) -> None:
    """
    Add a new delegated target role and update and sign metadata files.
    Automatically commit the changes if commit is set to True.

    Arguments:
        path: Path to the authentication repository.
        role: Name of the role which is to be added.
        parent_role: Name of the target role that is the new role's parent. Can be targets or another delegated role.
        paths: A list of target paths that are delegated to the new role.
        keys_number: Total number of signing keys
        threshold: Signature's threshold.
        yubikey: Specifies if the metadata file should be signed using a YubiKey.
        keystore: Location of the keystore files.
        scheme (optional): Signing scheme. Set to rsa-pkcs1v15-sha256 by default.
        auth_repo (optional): Instance of the authentication repository. Will be created if not passed into the function.
        commit (optional): Indicates if the changes should be committed and pushed automatically.
        prompt_for_keys (optional): Whether to ask the user to enter their key if it is not located inside the keystore directory.
        push (optional): Flag specifying whether to push to remote.
        skip_prompt (optional): A flag defining if the user will be asked if they want to generate new keys or reuse existing
            ones in case keystore files should be used. New keys will be generated by default.

    Side Effects:
        Initializes a new delegated targets role, signs metadata files, write changes to the disk and optionally commits.

    Returns:
        None
    """
    if auth_repo is None:
        auth_repo = AuthenticationRepository(path=path)
    existing_roles = auth_repo.get_all_targets_roles()
    existing_roles.extend(MAIN_ROLES)
    if role in existing_roles:
        taf_logger.log("NOTICE", "All roles already set up")
        return

    targets_parent_role = TargetsRole()
    if parent_role != "targets":
        targets_parent_role.name = parent_role
        targets_parent_role.paths = []

    new_role = TargetsRole()
    new_role.parent = targets_parent_role
    new_role.name = role
    new_role.paths = paths
    new_role.number = keys_number
    new_role.threshold = threshold
    new_role.yubikey = yubikey

    signing_keys, verification_keys = load_sorted_keys_of_new_roles(
        auth_repo=auth_repo,
        roles=new_role,
        yubikeys_data=None,
        keystore=keystore,
        skip_prompt=skip_prompt,
    )
    create_delegations(
        new_role, auth_repo, verification_keys, signing_keys, existing_roles
    )
    _update_role(
        auth_repo,
        targets_parent_role.name,
        keystore,
        scheme=scheme,
        prompt_for_keys=prompt_for_keys,
    )
    if commit:
        update_snapshot_and_timestamp(
            auth_repo, keystore, scheme=scheme, prompt_for_keys=prompt_for_keys
        )
        commit_msg = git_commit_message("add-role", role=role)
        commit_and_push(auth_repo, commit_msg=commit_msg, push=push)
    else:
        taf_logger.log("NOTICE", "\nPlease commit manually\n")


@log_on_start(DEBUG, "Adding new paths to role {delegated_role:s}", logger=taf_logger)
@log_on_end(DEBUG, "Finished adding new paths to role", logger=taf_logger)
@log_on_error(
    ERROR,
    "An error occurred while adding new paths to role {delegated_role:s}: {e}",
    logger=taf_logger,
    on_exceptions=TAFError,
    reraise=True,
)
def add_role_paths(
    paths: List[str],
    delegated_role: str,
    keystore: str,
    commit: Optional[bool] = True,
    auth_repo: Optional[AuthenticationRepository] = None,
    auth_path: Optional[str] = None,
    prompt_for_keys: Optional[bool] = False,
    push: Optional[bool] = True,
) -> None:
    """
    Adds additional delegated target paths to the specified role. That means that
    the role will be responsible for sining target files at those location going forward.

    Arguments:
        paths: A list of additional target paths that should be delegated to the role.
        delegated_role: Name of the targets role to which the new paths should be delegated.
        auth_path: Path to the authentication repository.
        keystore: Location of the keystore files.
        auth_repo (optional): Instance of the authentication repository. Will be created if not passed into the function.
        prompt_for_keys (optional): Whether to ask the user to enter their key if it is not located inside the keystore directory.
        commit (optional): Indicates if the changes should be committed and pushed automatically.
        push (optional): Flag specifying whether to push to remote.
    Side Effects:
        Updates the specified target role's parent and other metadata files (snapshot and timestamp),
        signs them, writes changes to disk and optionally commits everything.

    Returns:
        None
    """
    if auth_repo is None:
        auth_repo = AuthenticationRepository(path=auth_path)
    if not auth_repo.check_if_role_exists(delegated_role):
        raise TAFError(f"Role {delegated_role} does not exist")

    parent_role = auth_repo.find_delegated_roles_parent(delegated_role)
    parent_role_obj = _role_obj(parent_role, auth_repo)
    if isinstance(parent_role_obj, Targets):
        try:
            parent_role_obj.add_paths(paths, delegated_role)
        except tuf.exceptions.InvalidNameError:
            raise TAFError(
                "All delegated paths should be relative to targets directory."
            )
        _update_role(auth_repo, parent_role, keystore, prompt_for_keys=prompt_for_keys)
        if commit:
            update_snapshot_and_timestamp(
                auth_repo, keystore, prompt_for_keys=prompt_for_keys
            )
            commit_msg = git_commit_message(
                "add-role-paths", paths=", ".join(paths), role=delegated_role
            )
            commit_and_push(auth_repo, commit_msg=commit_msg, push=push)
        else:
            taf_logger.log("NOTICE", "\nPlease commit manually\n")
    else:
        taf_logger.error(
            f"Could not find parent role of role {delegated_role}. Check if its name was misspelled"
        )


@log_on_start(DEBUG, "Adding new roles", logger=taf_logger)
@log_on_end(DEBUG, "Finished adding new roles", logger=taf_logger)
@log_on_error(
    ERROR,
    "An error occurred while adding new roles: {e}",
    logger=taf_logger,
    on_exceptions=TAFError,
    reraise=True,
)
@check_if_clean
def add_multiple_roles(
    path: str,
    keystore: Optional[str] = None,
    roles_key_infos: Optional[str] = None,
    scheme: Optional[str] = DEFAULT_RSA_SIGNATURE_SCHEME,
    prompt_for_keys: Optional[bool] = False,
    commit: Optional[bool] = True,
    push: Optional[bool] = True,
) -> None:
    """
    Add new target roles and sign all metadata files given information stored in roles_key_infos
    dictionary or .json file.


    Arguments:
        path: Path to the authentication repository.
        keystore (optional): Location of the keystore files.
        roles_key_infos: Path to a json file which contains information about repository's roles and keys.
        scheme (optional): Signing scheme. Set to rsa-pkcs1v15-sha256 by default.
        prompt_for_keys (optional): Whether to ask the user to enter their key if it is not located inside the keystore directory.
        commit (optional): Indicates if the changes should be committed and pushed automatically.
        push (optional): Flag specifying whether to push to remote.
    Side Effects:
        Updates metadata files (parent of new roles, snapshot and timestamp) and creates new targets metadata files.
        Writes changes to disk.

    Returns:
        None
    """
    auth_repo = AuthenticationRepository(path=path)

    roles_keys_data_new = _initialize_roles_and_keystore_for_existing_repo(
        path, roles_key_infos, keystore
    )
    roles_data = auth_repo.generate_roles_description()
    roles_keys_data_current = from_dict(roles_data, RolesKeysData)

    new_roles, _ = compare_roles_data(roles_keys_data_current, roles_keys_data_new)

    parent_roles_names = {role.parent.name for role in new_roles}

    if not len(new_roles):
        taf_logger.log("NOTICE", "All roles already set up")
        return

    repository = auth_repo._repository
    existing_roles = [
        role.name for role in RolesIterator(roles_keys_data_current.roles)
    ]
    signing_keys, verification_keys = load_sorted_keys_of_new_roles(
        auth_repo=auth_repo,
        roles=roles_keys_data_new.roles,
        keystore=keystore,
        yubikeys_data=roles_keys_data_new.yubikeys,
        existing_roles=existing_roles,
    )

    create_delegations(
        roles_keys_data_new.roles.targets,
        repository,
        verification_keys,
        signing_keys,
        existing_roles=existing_roles,
    )
    for parent_role_name in parent_roles_names:
        _update_role(
            auth_repo,
            parent_role_name,
            keystore,
            scheme=scheme,
            prompt_for_keys=prompt_for_keys,
        )
    update_snapshot_and_timestamp(
        auth_repo, keystore, scheme=scheme, prompt_for_keys=prompt_for_keys
    )
    if commit:
        roles_names = [role.name for role in new_roles]
        commit_msg = git_commit_message("add-roles", roles=", ".join(roles_names))
        commit_and_push(auth_repo, commit_msg=commit_msg, push=push)
    else:
        taf_logger.log("NOTICE", "\nPlease commit manually\n")


@log_on_start(DEBUG, "Adding new signing key to roles", logger=taf_logger)
@log_on_end(DEBUG, "Finished adding new signing key to roles", logger=taf_logger)
@log_on_error(
    ERROR,
    "An error occurred while adding new signing key to roles: {e}",
    logger=taf_logger,
    on_exceptions=TAFError,
    reraise=True,
)
@check_if_clean
def add_signing_key(
    path: str,
    roles: List[str],
    pub_key_path: Optional[str] = None,
    keystore: Optional[str] = None,
    roles_key_infos: Optional[str] = None,
    scheme: Optional[str] = DEFAULT_RSA_SIGNATURE_SCHEME,
    commit: Optional[bool] = True,
    prompt_for_keys: Optional[bool] = False,
    push: Optional[bool] = True,
    commit_msg: Optional[str] = None,
) -> None:
    """
    Add a new signing key to the listed roles. Update root metadata if one or more roles is one of the main TUF roles,
    parent target role if one of the roles is a delegated target role and timestamp and snapshot in any case.

    Arguments:
        path: Path to the authentication repository.
        roles: A list of roles whose signing keys need to be extended.
        pub_key_path (optional): path to the file containing the public component of the new key. If not provided,
            it will be necessary to ender the key when prompted.
        keystore (optional): Location of the keystore files.
        roles_key_infos (optional): Path to a json file which contains information about repository's roles and keys.
        scheme (optional): Signing scheme. Set to rsa-pkcs1v15-sha256 by default.
        prompt_for_keys (optional): Whether to ask the user to enter their key if it is not located inside the keystore directory.
        commit (optional): Indicates if the changes should be committed and pushed automatically.
        push (optional): Flag specifying whether to push to remote.
        commit_msg(optional): Commit message. Will be necessary to enter it if not provided.
    Side Effects:
        Updates metadata files (parents of the affected roles, snapshot and timestamp).
        Writes changes to disk.

    Returns:
        None
    """
    auth_repo = AuthenticationRepository(path=path)
    non_existant_roles = []
    for role in roles:
        if not auth_repo.check_if_role_exists(role):
            non_existant_roles.append(role)
    if len(non_existant_roles):
        raise TAFError(f"Role(s) {', '.join(non_existant_roles)} do not exist")

    _, keystore, _ = _initialize_roles_and_keystore(
        roles_key_infos, keystore, enter_info=False
    )

    pub_key_pem = None
    if pub_key_path is not None:
        pub_key_pem_path = Path(pub_key_path)
        if pub_key_pem_path.is_file():
            pub_key_pem = Path(pub_key_path).read_text()

    if pub_key_pem is None:
        pub_key_pem = new_public_key_cmd_prompt(scheme)["keyval"]["public"]

    parent_roles = set()
    for role in roles:
        if auth_repo.is_valid_metadata_key(role, pub_key_pem):
            taf_logger.log(
                "NOTICE", f"Key already registered as signing key of role {role}"
            )
            continue

        auth_repo.add_metadata_key(role, pub_key_pem, scheme)

        if is_delegated_role(role):
            parent_role = auth_repo.find_delegated_roles_parent(role)
        else:
            parent_role = "root"

        parent_roles.add(parent_role)

    if not len(parent_roles):
        return

    auth_repo.unmark_dirty_roles(list(set(roles) - parent_roles))
    for parent_role in parent_roles:
        _update_role(
            auth_repo,
            parent_role,
            keystore,
            scheme=scheme,
            prompt_for_keys=prompt_for_keys,
        )

    update_snapshot_and_timestamp(
        auth_repo, keystore=keystore, scheme=scheme, prompt_for_keys=prompt_for_keys
    )

    if commit:
        # TODO after saving custom key ids is implemented, remove customization of the commit message
        # for now, it might be helpful to be able to specify which key was added
        # commit_msg = git_commit_message(
        #     "add-signing-key", role={role}
        # )
        commit_and_push(auth_repo, commit_msg=commit_msg, push=push)
    else:
        taf_logger.log("NOTICE", "\nPlease commit manually\n")


# TODO this is probably outdated, the format of the outputted roles_key_infos
def _enter_roles_infos(keystore: Optional[str], roles_key_infos: Optional[str]) -> Dict:
    """
    Ask the user to enter information taf roles and keys, including the location
    of keystore directory if not entered through an input parameter

    Arguments:
        keystore: Location of the keystore files.
        roles_key_infos: Path to a json file which contains information about repository's roles and keys.

    Side Effects:
        None

    Returns:
        A dictionary containing entered information about taf roles and keys (total number of keys per role,
        parent roles of roles, threshold of signatures per role, indicator if metadata should be signed using
        a yubikey for each role, key length and signing scheme for each role)
    """
    mandatory_roles = ["root", "targets", "snapshot", "timestamp"]
    role_key_infos: Dict = defaultdict(dict)
    infos_json: Dict = {}

    for role in mandatory_roles:
        role_key_infos[role] = _enter_role_info(role, role == "targets", keystore)
    infos_json["roles"] = role_key_infos

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
    if roles_key_infos is not None:
        try:
            path = Path(roles_key_infos)
            path.parent.mkdir(parents=True, exist_ok=True)
            Path(roles_key_infos).write_text(infos_json_str)
            taf_logger.log(
                "NOTICE",
                f"Configuration json written to {Path(roles_key_infos).absolute()}",
            )
        except Exception as e:
            taf_logger.error(e)
            _print_roles_key_infos(infos_json_str)
    else:
        print(infos_json_str)
    return infos_json


def _enter_role_info(
    role: str, is_targets_role: bool, keystore: Optional[str] = None
) -> Dict:
    role_info = {}
    keys_num = _read_val(int, f"number of {role} keys", "number")
    if keys_num is not None:
        role_info["number"] = keys_num

    role_info["yubikey"] = click.confirm(f"Store {role} keys on Yubikeys?")
    if role_info["yubikey"]:
        # in case of yubikeys, length and scheme have to have specific values
        role_info["length"] = 2048
        role_info["scheme"] = DEFAULT_RSA_SIGNATURE_SCHEME
    else:
        # if keystore is specified and contains keys corresponding to this role
        # get key size based on the public key
        keystore_length = 0
        if keystore is not None:
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
        delegated_roles: Dict = defaultdict(dict)
        while click.confirm(
            f"Add {'another' if len(delegated_roles) else 'a'} delegated targets role of role {role}?"
        ):
            role_name = _read_val(str, "role name", "role_name", True)
            delegated_paths: List[str] = []
            while not len(delegated_paths) or click.confirm("Enter another path?"):
                delegated_paths.append(
                    _read_val(
                        str,
                        f"path or glob pattern delegated to {role_name}",
                        "delegated_paths",
                        True,
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


def _read_val(input_type, name, param=None, required=False):
    default_value_msg = ""
    default_value = None
    if param is not None:
        default_value = DEFAULT_ROLE_SETUP_PARAMS[param]
        if default_value is not None:
            default_value_msg = f"(default {default_value}) "

    while True:
        try:
            val = input(f"Enter {name} and press ENTER {default_value_msg}")
            if not val:
                if not required:
                    return default_value
                else:
                    continue
            return input_type(val)
        except ValueError:
            pass


def _initialize_roles_and_keystore_for_existing_repo(
    path: str,
    roles_key_infos: Optional[str],
    keystore: Optional[str],
    enter_info: Optional[bool] = True,
) -> RolesKeysData:
    roles_key_infos_dict = read_input_dict(roles_key_infos)

    if not roles_key_infos_dict and enter_info:
        roles_key_infos_dict = _enter_roles_infos(None, roles_key_infos)
    roles_keys_data = from_dict(roles_key_infos_dict, RolesKeysData)
    keystore = keystore or roles_keys_data.keystore
    if keystore is None and path is not None:
        keystore_path = find_keystore(Path(path))
        if keystore_path:
            roles_keys_data.keystore = str(keystore_path)
    return roles_keys_data


def _initialize_roles_and_keystore(
    roles_key_infos: Optional[str],
    keystore: Optional[str],
    enter_info: Optional[bool] = True,
) -> Tuple[Dict, Optional[str], bool]:
    """
    Read information about roles and keys from a json file or ask the user to enter
    this information if not specified through a json file and enter_info is True.

    Arguments:
        roles_key_infos: A dictionary containing information about the roles:
            - total number of keys per role
            - their parent roles
            - threshold of signatures per role
            - should keys of a role be on Yubikeys or should a keystore files be used
            - scheme (the default scheme is rsa-pkcs1v15-sha256)
            - keystore path, if not specified via keystore option
        keystore: Location of the keystore files.
        enter_info (optional): Indicates if the user should be asked to enter information about the
        roles and keys if not specified. Set to True by default.


    Side Effects:
        None

    Returns:
        A dictionary containing entered information about taf roles and keys (total number of keys per role,
        parent roles of roles, threshold of signatures per role, indicator if metadata should be signed using
        a yubikey for each role, key length and signing scheme for each role) and keystore file path.
    """

    skip_prompt = False

    roles_key_infos_dict = read_input_dict(roles_key_infos)

    if not roles_key_infos_dict and enter_info:
        roles_key_infos_dict = _enter_roles_infos(None, roles_key_infos)

    # Check if all keys should be loaded from/stored to Yubikeys
    use_yubikeys = all(
        role_info.get("yubikey", False) for role_info in roles_key_infos_dict.values()
    )

    if not use_yubikeys and not keystore:
        keystore = roles_key_infos_dict.get("keystore")
        if not keystore:
            while True:
                use_keystore = (
                    input("Do you want to save/load keys from keystore files? [y/N]: ")
                    .strip()
                    .lower()
                )
                if use_keystore in ["y", "n"]:
                    break
            if use_keystore == "y":
                keystore = (
                    input("Enter keystore path (default ./keystore): ").strip()
                    or "./keystore"
                )
            else:
                taf_logger.log(
                    "NOTICE",
                    "Keys will be entered and then printed from the command line...",
                )

    if keystore is not None:
        keystore = resolve_keystore_path(keystore, roles_key_infos)
        roles_key_infos_dict["keystore"] = keystore

        while True:
            keystore_path = Path(keystore)
            if keystore_path.exists():
                break
            create_keystore = (
                input(
                    f"Keystore directory {keystore_path} does not exist. Do you want to create it? [y/N]: "
                )
                .strip()
                .lower()
            )
            if create_keystore == "y":
                keystore_path.mkdir(parents=True, exist_ok=True)
                roles_key_infos_dict["keystore"] = keystore
                print(f"Created keystore directory at {keystore}")
                skip_prompt = True
                break
            else:
                enter_new_path = (
                    input(
                        "Do you want to enter a different path to the keystore? [y/N]: "
                    )
                    .strip()
                    .lower()
                )
                if enter_new_path == "y":
                    keystore = input("New keystore path: ").strip()
                    keystore = resolve_keystore_path(keystore, roles_key_infos)
                    roles_key_infos_dict["keystore"] = keystore
                else:
                    raise KeystoreError("Keystore not found")

    return roles_key_infos_dict, keystore, skip_prompt


def _get_roles_key_size(role: str, keystore: str, keys_num: int) -> int:
    pub_key_name = f"{get_key_name(role, 1, keys_num)}.pub"
    key_path = str(Path(keystore, pub_key_name))
    return get_key_size(key_path)


@log_on_error(
    ERROR,
    "Could not list keys of {role:s}: {e}",
    logger=taf_logger,
    on_exceptions=TAFError,
    reraise=True,
)
def list_keys_of_role(
    path: str,
    role: str,
) -> List[str]:
    """
     Print information about signing keys of role. If a certificate whose name matches
     a key's id exists, include information contained by that certificate (like name and valid to/from dates)

     Arguments:
         path: Path to the authentication repository.
         role: Name of the role which is to be removed.

    Side Effects:
         None

     Returns:
         None
    """
    auth_repo = AuthenticationRepository(path=path)
    key_ids = auth_repo.get_role_keys(role=role)
    if key_ids is None:
        raise TAFError(f"Role {role} does not exist")

    return [
        str(get_metadata_key_info(auth_repo.certs_dir, key_id)) for key_id in key_ids
    ]


@log_on_start(DEBUG, "Removing role {role:s}", logger=taf_logger)
@log_on_end(DEBUG, "Finished removing the role", logger=taf_logger)
@log_on_error(
    ERROR,
    "An error occurred while removing role {role:s}: {e}",
    logger=taf_logger,
    on_exceptions=TAFError,
    reraise=True,
)
@check_if_clean
def remove_role(
    path: str,
    role: str,
    keystore: str,
    scheme: Optional[str] = DEFAULT_RSA_SIGNATURE_SCHEME,
    commit: Optional[bool] = True,
    remove_targets: Optional[bool] = False,
    auth_repo: Optional[AuthenticationRepository] = None,
    prompt_for_keys: Optional[bool] = False,
    push: Optional[bool] = True,
) -> None:
    """
    Remove a delegated target role and update and sign metadata files.
    Automatically commit the changes if commit is set to True.
    It is not possible to remove any of the main TUF roles

    Arguments:
        path: Path to the authentication repository.
        role: Name of the role which is to be removed.
        keystore: Location of the keystore files.
        scheme (optional): Signing scheme. Set to rsa-pkcs1v15-sha256 by default.
        commit (optional): Indicates if the changes should be committed and pushed automatically.
        remove_targets (optional): Indicates if target files should be removed to, or signed by the parent role.
            Set to False by default.
        auth_repo (optional): Instance of the authentication repository. Will be created if not passed into the function.
        prompt_for_keys (optional): Whether to ask the user to enter their key if it is not located inside the keystore directory.
        push (optional): Flag specifying whether to push to remote.
    Side Effects:
        Updates metadata files, optionally deletes target files, writes changes to disk and optionally commits.

    Returns:
        None
    """
    if role in MAIN_ROLES:
        taf_logger.error(
            f"Cannot remove role {role}. It is one of the roles required by the TUF specification"
        )
        return

    if auth_repo is None:
        auth_repo = AuthenticationRepository(path=path)

    parent_role = auth_repo.find_delegated_roles_parent(role)
    if parent_role is None:
        taf_logger.error("Role is not among delegated roles")
        return
    parent_role_obj = _role_obj(parent_role, auth_repo)
    if not isinstance(parent_role_obj, Targets):
        taf_logger.error(f"Could not find parent targets role of role {role}.")
        return

    roleinfo = tuf.roledb.get_roleinfo(parent_role, auth_repo.name)
    added_targets_data: Dict = {}
    removed_targets = []
    for delegations_data in roleinfo["delegations"]["roles"]:
        if delegations_data["name"] == role:
            paths = delegations_data["paths"]
            for target_path in paths:
                target_file_path = Path(path, TARGETS_DIRECTORY_NAME, target_path)
                if target_file_path.is_file():
                    if remove_targets:
                        os.unlink(str(target_file_path))
                        removed_targets.append(str(target_file_path))
                    else:
                        added_targets_data[target_file_path] = {}
                else:
                    # try glob pattern traversal
                    full_pattern = str(Path(path, TARGETS_DIRECTORY_NAME, target_path))
                    matching_files = glob.glob(full_pattern)
                    for file_path in matching_files:
                        if remove_targets:
                            os.unlink(str(file_path))
                            removed_targets.append(file_path)
                        else:
                            added_targets_data[file_path] = {}
            break

    parent_role_obj.revoke(role)

    _update_role(
        auth_repo, role=parent_role, keystore=keystore, prompt_for_keys=prompt_for_keys
    )
    if len(added_targets_data):
        removed_targets_data: Dict = {}
        update_target_metadata(
            auth_repo,
            added_targets_data,
            removed_targets_data,
            keystore,
            write=False,
            scheme=DEFAULT_RSA_SIGNATURE_SCHEME,
            prompt_for_keys=prompt_for_keys,
        )

    # if targets should be deleted, also removed them from repositories.json
    if len(removed_targets):
        repositories_json = repositoriesdb.load_repositories_json(auth_repo)
        if repositories_json is not None:
            repositories = repositories_json["repositories"]
            for removed_target in removed_targets:
                if removed_target in repositories:
                    repositories.pop(removed_target)

                # update content of repositories.json before updating targets metadata
                Path(auth_repo.path, REPOSITORIES_JSON_PATH).write_text(
                    json.dumps(repositories_json, indent=4)
                )

    update_snapshot_and_timestamp(
        auth_repo, keystore, scheme=scheme, prompt_for_keys=prompt_for_keys
    )
    if commit:
        commit_msg = git_commit_message("remove-role", role=role)
        commit_and_push(auth_repo, commit_msg=commit_msg, push=push)
    else:
        taf_logger.log("NOTICE", "Please commit manually")


@log_on_start(DEBUG, "Removing delegated paths", logger=taf_logger)
@log_on_end(DEBUG, "Finished removing delegated paths", logger=taf_logger)
@log_on_error(
    ERROR,
    "An error occurred while removing roles: {e}",
    logger=taf_logger,
    on_exceptions=TAFError,
    reraise=True,
)
def remove_paths(
    path: str,
    paths: List[str],
    keystore: str,
    commit: Optional[bool] = True,
    prompt_for_keys: Optional[bool] = False,
    push: Optional[bool] = True,
) -> bool:
    """
    Remove delegated paths. Update parent roles of the roles associated with the removed paths,
    as well as snapshot and timestamp. Optionally commit the changes.

    Arguments:
        path:  Path to the authentication repository.
        paths: Paths to be removed.
        keystore: Location of the keystore files.
        commit (optional): Indicates if the changes should be committed and pushed automatically.
        prompt_for_keys (optional): Whether to ask the user to enter their key if it is not located inside the keystore directory.
        push (optional): Flag specifying whether to push to remote.
    Side Effects:
        Updates metadata files, writes changes to disk and optionally commits them.

    Returns:
        True if the delegation existed, False otherwise
    """
    auth_repo = AuthenticationRepository(path=path)
    delegation_existed = False
    for path_to_remove in paths:
        delegated_role = auth_repo.get_role_from_target_paths([path_to_remove])
        if delegated_role != "targets":
            parent_role = auth_repo.find_delegated_roles_parent(delegated_role)
            # parent_role_obj = _role_obj(parent_role, auth_repo)
            current_delegation_existed = _remove_path_from_role_info(
                path_to_remove, parent_role, delegated_role, auth_repo
            )
            delegation_existed = delegation_existed or current_delegation_existed
            if current_delegation_existed:
                _update_role(
                    auth_repo, parent_role, keystore, prompt_for_keys=prompt_for_keys
                )
    if delegation_existed and commit:
        update_snapshot_and_timestamp(
            auth_repo, keystore, prompt_for_keys=prompt_for_keys
        )
        commit_msg = git_commit_message(
            "remove-role-paths", paths=", ".join(paths), role=delegated_role
        )
        commit_and_push(auth_repo, commit_msg=commit_msg, push=push)
    elif delegation_existed:
        taf_logger.log("NOTICE", "\nPlease commit manually\n")
    return delegation_existed


def _remove_path_from_role_info(
    path_to_remove: str,
    parent_role: str,
    delegated_role: str,
    auth_repo: AuthenticationRepository,
) -> bool:
    """
    Remove path from delegated paths if directly listed.

    E.g. if delegated paths are

    "paths": [
      "namespace/repo1",
      "namespace/repo2"
    ]

    Arguments:
        path_to_remove: path to be removed from delegated paths
        parent_role: Parent role's name
        delegated_role: Delegated role's name
        auth_repo: Authentication repository

    and namespace/repo1 is being removed

    Returns:
        True if path was directly specified as a delegated path, False otherwise
    """

    auth_repo.reload_tuf_repository()
    delegation_exists = False
    roleinfo = tuf.roledb.get_roleinfo(parent_role, auth_repo.name)
    for delegations_data in roleinfo["delegations"]["roles"]:
        if delegations_data["name"] == delegated_role:
            delegations_paths = delegations_data["paths"]
            if path_to_remove in delegations_paths:
                delegations_paths.remove(path_to_remove)
                delegation_exists = True
            else:
                taf_logger.log("NOTICE", f"{path_to_remove} not in delegated paths")
            break
    if delegation_exists:
        tuf.roledb.update_roleinfo(
            parent_role, roleinfo, repository_name=auth_repo.name
        )
    return delegation_exists


def _update_role(
    auth_repo: AuthenticationRepository,
    role: str,
    keystore: Optional[str],
    scheme: Optional[str] = DEFAULT_RSA_SIGNATURE_SCHEME,
    prompt_for_keys: Optional[bool] = False,
) -> None:
    """
    Update the specified role's metadata's expiration date, load the signing keys
    from either a keystore file or yubikey and sign the file without updating
    snapshot and timestamp and writing changes to disk
    """
    loaded_yubikeys: Dict = {}
    keystore_keys, yubikeys = load_signing_keys(
        auth_repo,
        role,
        loaded_yubikeys,
        keystore,
        scheme=scheme,
        prompt_for_keys=prompt_for_keys,
    )
    if len(keystore_keys):
        auth_repo.update_role_keystores(role, keystore_keys, write=False)
    if len(yubikeys):
        auth_repo.update_role_yubikeys(role, yubikeys, write=False)


def list_roles(auth_repo: AuthenticationRepository) -> None:
    """
    Print a list of all defined roles with their thresholds and parent roles.
    """

    def print_role_and_children(role: str, indent: int = 0) -> None:
        threshold = auth_repo.get_role_threshold(role)
        indent_str = " " * indent
        print(f"{indent_str}{role} (threshold: {threshold})")

        # Retrieve children (delegated roles)
        delegations = auth_repo.get_delegations_info(role)
        if delegations:
            children = [role_info["name"] for role_info in delegations.get("roles", [])]
            for child in children:
                print_role_and_children(child, indent + 2)

    for role in MAIN_ROLES:
        print_role_and_children(role)
