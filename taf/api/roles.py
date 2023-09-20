from logging import DEBUG, ERROR, INFO
import os
from typing import Dict, List, Optional
import click
from collections import defaultdict
from functools import partial
import json
from pathlib import Path
from logdecorator import log_on_end, log_on_error, log_on_start
from taf.api.utils import check_if_clean, commit_and_push
from taf.exceptions import TAFError
from taf.models.converter import from_dict
from taf.models.types import RolesIterator
from taf.models.types import DelegatedRole, Role, TargetsRole
from taf.repositoriesdb import REPOSITORIES_JSON_PATH
from taf.yubikey import get_key_serial_by_id
from tuf.repository_tool import TARGETS_DIRECTORY_NAME, Metadata
import tuf.roledb
import taf.repositoriesdb as repositoriesdb
from taf.keys import (
    get_key_name,
    get_metadata_key_info,
    load_signing_keys,
    load_sorted_keys_of_new_roles,
)
from taf.api.metadata import update_snapshot_and_timestamp, update_target_metadata
from taf.auth_repo import AuthenticationRepository
from taf.constants import (
    DEFAULT_ROLE_SETUP_PARAMS,
    YUBIKEY_EXPIRATION_DATE,
    DEFAULT_RSA_SIGNATURE_SCHEME,
)
from taf.keystore import default_keystore_path, new_public_key_cmd_prompt
from taf.repository_tool import (
    Repository,
    is_delegated_role,
    yubikey_signature_provider,
)
from taf.utils import get_key_size, read_input_dict
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

    Side Effects:
        Initializes a new delegated targets role, signs metadata files, write changes to the disk and optionally commits.

    Returns:
        None
    """
    if auth_repo is None:
        auth_repo = AuthenticationRepository(path=path)
    path = Path(path)
    existing_roles = auth_repo.get_all_targets_roles()
    existing_roles.extend(MAIN_ROLES)
    if role in existing_roles:
        taf_logger.info("All roles already set up")
        return

    if parent_role == "targets":
        parent_role = TargetsRole()
    else:
        parent_role = DelegatedRole(name=parent_role)

    new_role = DelegatedRole(
        parent=parent_role,
        name=role,
        paths=paths,
        number=keys_number,
        threshold=threshold,
        yubikey=yubikey,
    )

    signing_keys, verification_keys = load_sorted_keys_of_new_roles(
        auth_repo=auth_repo,
        roles=new_role,
        yubikeys_data=None,
        keystore=keystore,
    )
    create_delegations(
        new_role, auth_repo, verification_keys, signing_keys, existing_roles
    )
    _update_role(
        auth_repo,
        parent_role.name,
        keystore,
        scheme=scheme,
        prompt_for_keys=prompt_for_keys,
    )
    if commit:
        update_snapshot_and_timestamp(
            auth_repo, keystore, scheme=scheme, prompt_for_keys=prompt_for_keys
        )
        commit_and_push(auth_repo)
    else:
        taf_logger.info("\nPlease commit manually\n")


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
    Side Effects:
        Updates the specified target role's parent and other metadata files (snapshot and timestamp),
        signs them, writes changes to disk and optionally commits everything.

    Returns:
        None
    """
    if auth_repo is None:
        auth_repo = AuthenticationRepository(path=auth_path)
    parent_role = auth_repo.find_delegated_roles_parent(delegated_role)
    parent_role_obj = _role_obj(parent_role, auth_repo)
    parent_role_obj.add_paths(paths, delegated_role)
    _update_role(auth_repo, parent_role, keystore, prompt_for_keys=prompt_for_keys)
    if commit:
        update_snapshot_and_timestamp(
            auth_repo, keystore, prompt_for_keys=prompt_for_keys
        )
        commit_and_push(auth_repo)
    else:
        taf_logger.info("\nPlease commit manually\n")


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
def add_roles(
    path: str,
    keystore: Optional[str] = None,
    roles_key_infos: Optional[str] = None,
    scheme: Optional[str] = DEFAULT_RSA_SIGNATURE_SCHEME,
    prompt_for_keys: Optional[bool] = False,
    commit: Optional[bool] = True,
) -> None:
    """
    Add new target roles and sign all metadata files given information stored in roles_key_infos
    dictionary or .json file

    Arguments:
        path: Path to the authentication repository.
        keystore (optional): Location of the keystore files.
        roles_key_infos: Path to a json file which contains information about repository's roles and keys.
        auth_repo (optional): Instance of the authentication repository. Will be created if not passed into the function.
        scheme (optional): Signing scheme. Set to rsa-pkcs1v15-sha256 by default.
        prompt_for_keys (optional): Whether to ask the user to enter their key if it is not located inside the keystore directory.
        commit (optional): Indicates if the changes should be committed and pushed automatically.

    Side Effects:
        Updates metadata files (parent of new roles, snapshot and timestamp) and creates new targets metadata files.
        Writes changes to disk.

    Returns:
        None
    """
    auth_repo = AuthenticationRepository(path=path)
    path = Path(path)

    roles_key_infos, keystore = _initialize_roles_and_keystore(
        roles_key_infos, keystore
    )

    roles_keys_data = from_dict(roles_key_infos, RolesKeysData)

    new_roles = []
    existing_roles = auth_repo.get_all_targets_roles()
    main_roles = ["root", "snapshot", "timestamp"]
    existing_roles.extend(main_roles)

    new_roles = [
        role
        for role in RolesIterator(roles_keys_data.roles.targets, skip_top_role=True)
        if role.name not in existing_roles
    ]

    parent_roles_names = {role.parent.name for role in new_roles}

    if not len(new_roles):
        taf_logger.info("All roles already set up")
        return

    repository = auth_repo._repository
    signing_keys, verification_keys = load_sorted_keys_of_new_roles(
        auth_repo=auth_repo,
        roles=roles_keys_data.roles,
        keystore=keystore,
        yubikeys_data=roles_keys_data.yubikeys,
        existing_roles=existing_roles,
    )

    create_delegations(
        roles_keys_data.roles.targets,
        repository,
        verification_keys,
        signing_keys,
        existing_roles,
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
        commit_and_push(auth_repo)
    else:
        taf_logger.info("\nPlease commit manually\n")


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

    Side Effects:
        Updates metadata files (parents of the affected roles, snapshot and timestamp).
        Writes changes to disk.

    Returns:
        None
    """
    auth_repo = AuthenticationRepository(path=path)
    roles_key_infos, keystore = _initialize_roles_and_keystore(
        roles_key_infos, keystore, enter_info=False
    )

    pub_key_pem = None
    if pub_key_path is not None:
        pub_key_path = Path(pub_key_path)
        if pub_key_path.is_file():
            pub_key_pem = Path(pub_key_path).read_text()

    if pub_key_pem is None:
        pub_key_pem = new_public_key_cmd_prompt(scheme)["keyval"]["public"]

    parent_roles = set()
    for role in roles:
        if auth_repo.is_valid_metadata_key(role, pub_key_pem):
            taf_logger.info(f"Key already registered as signing key of role {role}")
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
        commit_and_push(auth_repo)
    else:
        taf_logger.info("\nPlease commit manually\n")


def _enter_roles_infos(keystore: str, roles_key_infos: str) -> Dict:
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
                taf_logger.info(f"{keystore} does not exist")
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
            taf_logger.info(
                f"Configuration json written to {Path(roles_key_infos).absolute()}"
            )
        except Exception as e:
            taf_logger.error(e)
            _print_roles_key_infos(infos_json_str)
    else:
        print(infos_json_str)
    return infos_json


def _enter_role_info(role: str, is_targets_role: bool, keystore: str) -> Dict:
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


def _initialize_roles_and_keystore(
    roles_key_infos: str, keystore: str, enter_info: Optional[bool] = True
):
    """
    Read information about roles and keys from a json file or ask the user to enter
    this information if not specified through a json file enter_info is True

    Arguments:
        roles_key_infos: A dictionary containing information about the roles:
            - total number of keys per role
            - their parent roles
            - threshold of signatures per role
            - should keys of a role be on Yubikeys or should a keystore files be used
            - scheme (the default scheme is rsa-pkcs1v15-sha256)
            - keystore path, if not specified via keystore option
        keystore: Location of the keystore files.
        enter_info (optional): Indicates if the user should be asked to enter information about the.
        roles and keys if not specified. Set to True by default.

    Side Effects:
        None

    Returns:
        A dictionary containing entered information about taf roles and keys (total number of keys per role,
        parent roles of roles, threshold of signatures per role, indicator if metadata should be signed using
        a yubikey for each role, key length and signing scheme for each role) and keystore file path
    """
    roles_key_infos_dict = read_input_dict(roles_key_infos)
    if keystore is None:
        # if keystore path is specified in roles_key_infos and is a relative path
        # it should be relative to the location of the file
        # roles_key_infos can either be path to a json file, or a dictionary (or not provided)
        keystore = roles_key_infos_dict.get("keystore") or default_keystore_path()
        if roles_key_infos is not None and type(roles_key_infos) == str:
            roles_key_infos_path = Path(roles_key_infos)
            if roles_key_infos_path.is_file() and "keystore" in roles_key_infos_dict:
                keystore_path = (
                    Path(roles_key_infos_dict["keystore"]).expanduser().resolve()
                )
                if not keystore_path.is_absolute():
                    keystore_path = (
                        roles_key_infos_path.parent / keystore_path
                    ).resolve()
                    keystore = str(keystore_path)

    if enter_info and not len(roles_key_infos_dict):
        # ask the user to enter roles, number of keys etc.
        roles_key_infos_dict = _enter_roles_infos(keystore, roles_key_infos)

    return roles_key_infos_dict, keystore


@log_on_start(INFO, "Creating delegations", logger=taf_logger)
@log_on_end(DEBUG, "Finished creating delegations", logger=taf_logger)
def create_delegations(
    role: str,
    repository: AuthenticationRepository,
    verification_keys: Dict,
    signing_keys: Dict,
    existing_roles: Optional[bool] = None,
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
    skip_top_role = isinstance(role, TargetsRole)
    for delegated_role in RolesIterator(role, skip_top_role=skip_top_role):
        parent_role_obj = _role_obj(delegated_role.parent.name, repository)
        if delegated_role.name in existing_roles:
            taf_logger.info(f"Role {delegated_role.name} already set up.")
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


def _get_roles_key_size(role: str, keystore: str, keys_num: int) -> int:
    pub_key_name = f"{get_key_name(role, 1, keys_num)}.pub"
    key_path = str(Path(keystore, pub_key_name))
    return get_key_size(key_path)


def _role_obj(role: str, repository: Repository, parent: str = None) -> Metadata:
    """
    Return role TUF object based on its name
    """
    if isinstance(repository, Repository):
        repository = repository._repository
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
) -> None:
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
    for key_id in key_ids:
        taf_logger.info(f"{get_metadata_key_info(auth_repo.certs_dir, key_id)}")


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

    Side Effects:
        Updates metadata files, optionally deletes target files, writes changes to disk and optionally commits.

    Returns:
        None
    """
    if role in MAIN_ROLES:
        taf_logger.info(
            f"Cannot remove role {role}. It is one of the roles required by the TUF specification"
        )
        return

    if auth_repo is None:
        auth_repo = AuthenticationRepository(path=path)

    parent_role = auth_repo.find_delegated_roles_parent(role)
    if parent_role is None:
        taf_logger.info("Role is not among delegated roles")
        return

    roleinfo = tuf.roledb.get_roleinfo(parent_role, auth_repo.name)
    added_targets_data = {}
    removed_targets = []
    for delegations_data in roleinfo["delegations"]["roles"]:
        if delegations_data["name"] == role:
            paths = delegations_data["paths"]
            for path in paths:
                target_file_path = Path(path, TARGETS_DIRECTORY_NAME, path)
                if target_file_path.is_file():
                    if remove_targets:
                        os.unlink(str(target_file_path))
                        removed_targets.append(path)
                    else:
                        added_targets_data[path] = {}
            break

    parent_role_obj = _role_obj(parent_role, auth_repo)
    parent_role_obj.revoke(role)

    _update_role(
        auth_repo, role=parent_role, keystore=keystore, prompt_for_keys=prompt_for_keys
    )
    if len(added_targets_data):
        removed_targets_data = {}
        update_target_metadata(
            auth_repo,
            added_targets_data,
            removed_targets_data,
            keystore,
            write=False,
            scheme=DEFAULT_RSA_SIGNATURE_SCHEME,
            update_target_metadata=update_target_metadata,
            prompt_for_keys=prompt_for_keys,
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

    update_snapshot_and_timestamp(
        auth_repo, keystore, scheme=scheme, prompt_for_keys=prompt_for_keys
    )
    if commit:
        commit_and_push(auth_repo)
    else:
        taf_logger.info("Please commit manually")


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
        commit_and_push(auth_repo)
    elif delegation_existed:
        taf_logger.info("\nPlease commit manually\n")
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
                taf_logger.info(f"{path_to_remove} not in delegated paths")
            break
    if delegation_exists:
        tuf.roledb.update_roleinfo(
            parent_role, roleinfo, repository_name=auth_repo.name
        )
    return delegation_exists


@log_on_start(INFO, "Setting up role {role.name:s}", logger=taf_logger)
@log_on_end(DEBUG, "Finished setting up role {role.name:s}", logger=taf_logger)
def setup_role(
    role: Role,
    repository: Repository,
    verification_keys: Dict,
    signing_keys: Optional[Dict] = None,
    parent: Optional[str] = None,
) -> None:
    """
    Initialize a new role, add signing and verification keys.
    """
    role_obj = _role_obj(role.name, repository, parent)
    role_obj.threshold = role.threshold
    if not role.is_yubikey:
        for public_key, private_key in zip(verification_keys, signing_keys):
            role_obj.add_verification_key(public_key)
            role_obj.load_signing_key(private_key)
    else:
        for key_name, key in zip(role.yubikeys, verification_keys):
            role_obj.add_verification_key(key, expires=YUBIKEY_EXPIRATION_DATE)
            # check if yubikey loaded
            if get_key_serial_by_id(key_name):
                role_obj.add_external_signature_provider(
                    key, partial(yubikey_signature_provider, key_name, key["keyid"])
                )


def _update_role(
    auth_repo: AuthenticationRepository,
    role: str,
    keystore: str,
    scheme: Optional[str] = DEFAULT_RSA_SIGNATURE_SCHEME,
    prompt_for_keys: Optional[bool] = False,
) -> None:
    """
    Update the specified role's metadata's expiration date, load the signing keys
    from either a keystore file or yubikey and sign the file without updating
    snapshot and timestamp and writing changes to disk
    """
    keystore_keys, yubikeys = load_signing_keys(
        auth_repo, role, keystore, scheme=scheme, prompt_for_keys=prompt_for_keys
    )
    if len(keystore_keys):
        auth_repo.update_role_keystores(role, keystore_keys, write=False)
    if len(yubikeys):
        auth_repo.update_role_yubikeys(role, yubikeys, write=False)
