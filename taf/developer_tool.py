import json
from binascii import hexlify
from collections import defaultdict
from functools import partial
from getpass import getpass
from pathlib import Path

import click
import securesystemslib
import securesystemslib.exceptions
from taf.api.roles import _create_delegations, _initialize_roles_and_keystore, _role_obj
from taf.keys import (
    get_key_name,
    load_signing_keys,
    setup_roles_keys,
)
from taf.api.metadata import update_snapshot_and_timestamp, update_target_metadata
from taf.api.targets import (
    _save_top_commit_of_repo_to_target,
)

try:
    import taf.yubikey as yk
except ImportError:
    yk = YubikeyMissingLibrary()


from tuf.repository_tool import (
    TARGETS_DIRECTORY_NAME,
    create_new_repository,
)

from taf import YubikeyMissingLibrary
from taf.auth_repo import AuthenticationRepository
from taf.constants import (
    DEFAULT_ROLE_SETUP_PARAMS,
    DEFAULT_RSA_SIGNATURE_SCHEME,
    YUBIKEY_EXPIRATION_DATE,
)
from taf.exceptions import KeystoreError, TargetsMetadataUpdateError
from taf.git import GitRepository
from taf.repository_tool import (
    Repository,
    yubikey_signature_provider,
)
import taf.repositoriesdb as repositoriesdb


def add_roles(
    repo_path,
    keystore=None,
    roles_key_infos=None,
    scheme=DEFAULT_RSA_SIGNATURE_SCHEME,
):
    yubikeys = defaultdict(dict)
    auth_repo = AuthenticationRepository(path=repo_path)
    repo_path = Path(repo_path)

    roles_key_infos, keystore = _initialize_roles_and_keystore(
        roles_key_infos, keystore
    )

    new_roles = []
    taf_repo = Repository(repo_path)
    existing_roles = taf_repo.get_all_targets_roles()
    main_roles = ["root", "snapshot", "timestamp", "targets"]
    existing_roles.extend(main_roles)

    # allow specification of roles without putting them inside targets delegations map
    # ensuring that it is possible to specify only delegated roles
    # since creation of delegations expects that structure, place the roles inside targets/delegations
    delegations_info = {}
    for role_name, role_data in dict(roles_key_infos["roles"]).items():
        if role_name not in main_roles:
            roles_key_infos["roles"].pop(role_name)
            delegations_info[role_name] = role_data
    roles_key_infos["roles"].setdefault("targets", {"delegations": {}})[
        "delegations"
    ].update(delegations_info)

    # find all existing roles which are parents of the newly added roles
    # they should be signed after the delegations are created
    roles = [
        (role_name, role_data)
        for role_name, role_data in roles_key_infos["roles"].items()
    ]
    parent_roles = set()
    while len(roles):
        role_name, role_data = roles.pop()
        for delegated_role, delegated_role_data in role_data.get(
            "delegations", {}
        ).items():
            if delegated_role not in existing_roles:
                if role_name not in new_roles:
                    parent_roles.add(role_name)
                new_roles.append(delegated_role)
            roles.append((delegated_role, delegated_role_data))

    if not len(new_roles):
        print("All roles already set up")
        return

    repository = taf_repo._repository
    roles_infos = roles_key_infos.get("roles")
    signing_keys, verification_keys = _load_sorted_keys_of_new_roles(
        auth_repo, roles_infos, taf_repo, keystore, yubikeys, existing_roles
    )
    _create_delegations(
        roles_infos, repository, verification_keys, signing_keys, existing_roles
    )
    for parent_role in parent_roles:
        _update_role(taf_repo, parent_role, keystore, roles_infos, scheme=scheme)
    update_snapshot_and_timestamp(taf_repo, keystore, roles_infos, scheme=scheme)


def update_target_repos_from_repositories_json(
    repo_path,
    library_dir,
    keystore,
    add_branch=True,
    scheme=DEFAULT_RSA_SIGNATURE_SCHEME,
):
    """
    <Purpose>
        Create or update target files by reading the latest commit's repositories.json
    <Arguments>
        repo_path:
        Authentication repository's location
        library_dir:
        Directory where target repositories and, optionally, authentication repository are locate
        namespace:
        Namespace used to form the full name of the target repositories. Each target repository
        add_branch:
        Indicates whether to add the current branch's name to the target file
    """
    repo_path = Path(repo_path).resolve()
    if library_dir is None:
        library_dir = repo_path.parent.parent
    else:
        library_dir = Path(library_dir)
    auth_repo_targets_dir = repo_path / TARGETS_DIRECTORY_NAME
    repositories_json = json.loads(
        Path(auth_repo_targets_dir / "repositories.json").read_text()
    )
    for repo_name in repositories_json.get("repositories"):
        _save_top_commit_of_repo_to_target(
            library_dir, repo_name, repo_path, add_branch
        )
    register_target_files(repo_path, keystore, None, True, scheme)


def _check_if_can_create_repository(auth_repo):
    repo_path = Path(auth_repo.path)
    if repo_path.is_dir():
        # check if there is non-empty metadata directory
        if auth_repo.metadata_path.is_dir() and any(auth_repo.metadata_path.iterdir()):
            if auth_repo.is_git_repository:
                print(
                    f'"{repo_path}" is a git repository containing the metadata directory. Generating new metadata files could make the repository invalid. Aborting.'
                )
                return False
            if not click.confirm(
                f'Metadata directory found inside "{repo_path}". Recreate metadata files?'
            ):
                return False
    return True


def create_repository(
    repo_path, keystore=None, roles_key_infos=None, commit=False, test=False
):
    """
    <Purpose>
        Create a new authentication repository. Generate initial metadata files.
        The initial targets metadata file is empty (does not specify any targets).
    <Arguments>
        repo_path:
        Authentication repository's location
        targets_directory:
        Directory which contains target repositories
        keystore:
        Location of the keystore files
        roles_key_infos:
        A dictionary whose keys are role names, while values contain information about the keys.
        commit:
        Indicates if the changes should be automatically committed
        test:
        Indicates if the created repository is a test authentication repository
    """
    yubikeys = defaultdict(dict)
    auth_repo = AuthenticationRepository(path=repo_path)
    repo_path = Path(repo_path)

    if not _check_if_can_create_repository(auth_repo):
        return

    roles_key_infos, keystore = _initialize_roles_and_keystore(
        roles_key_infos, keystore
    )

    repository = create_new_repository(str(auth_repo.path))
    roles_infos = roles_key_infos.get("roles")
    signing_keys, verification_keys = _load_sorted_keys_of_new_roles(
        auth_repo, roles_infos, repository, keystore, yubikeys
    )
    # set threshold and register keys of main roles
    # we cannot do the same for the delegated roles until delegations are created
    for role_name, role_key_info in roles_infos.items():
        threshold = role_key_info.get("threshold", 1)
        is_yubikey = role_key_info.get("yubikey", False)
        _setup_role(
            role_name,
            threshold,
            is_yubikey,
            repository,
            verification_keys[role_name],
            signing_keys.get(role_name),
        )

    _create_delegations(roles_infos, repository, verification_keys, signing_keys)

    # if the repository is a test repository, add a target file called test-auth-repo
    if test:
        test_auth_file = (
            Path(auth_repo.path, auth_repo.targets_path) / auth_repo.TEST_REPO_FLAG_FILE
        )
        test_auth_file.touch()

    # register and sign target files (if any)
    try:
        taf_repository = Repository(repo_path)
        taf_repository._tuf_repository = repository
        register_target_files(
            repo_path, keystore, roles_key_infos, commit=commit, taf_repo=taf_repository
        )
    except TargetsMetadataUpdateError:
        # if there are no target files
        repository.writeall()

    print("Created new authentication repository")

    if commit:
        auth_repo.init_repo()
        commit_message = input("\nEnter commit message and press ENTER\n\n")
        auth_repo.commit(commit_message)


def _load_sorted_keys_of_new_roles(
    auth_repo, roles_infos, repository, keystore, yubikeys, existing_roles=None
):
    def _sort_roles(key_info, repository):
        # load keys not stored on YubiKeys first, to avoid entering pins
        # if there is somethig wrong with keystore files
        keystore_roles = []
        yubikey_roles = []
        for role_name, role_key_info in key_info.items():
            if not role_key_info.get("yubikey", False):
                keystore_roles.append((role_name, role_key_info))
            else:
                yubikey_roles.append((role_name, role_key_info))
            if "delegations" in role_key_info:
                delegated_keystore_role, delegated_yubikey_roles = _sort_roles(
                    role_key_info["delegations"]["roles"], repository
                )
                keystore_roles.extend(delegated_keystore_role)
                yubikey_roles.extend(delegated_yubikey_roles)
        return keystore_roles, yubikey_roles

    # load and/or generate all keys first
    if existing_roles is None:
        existing_roles = []
    try:
        keystore_roles, yubikey_roles = _sort_roles(roles_infos, repository)
        signing_keys = {}
        verification_keys = {}
        for role_name, key_info in keystore_roles:
            if role_name in existing_roles:
                continue
            keystore_keys, _ = setup_roles_keys(
                role_name, key_info, repository, keystore=keystore
            )
            for public_key, private_key in keystore_keys:
                signing_keys.setdefault(role_name, []).append(private_key)
                verification_keys.setdefault(role_name, []).append(public_key)

        for role_name, key_info in yubikey_roles:
            if role_name in existing_roles:
                continue
            _, yubikey_keys = setup_roles_keys(
                role_name,
                key_info,
                repository,
                certs_dir=auth_repo.certs_dir,
                yubikeys=yubikeys,
            )
            verification_keys[role_name] = yubikey_keys
        return signing_keys, verification_keys
    except KeystoreError as e:
        print(f"Creation of repository failed: {e}")
        return


def register_target_files(
    repo_path,
    keystore=None,
    roles_key_infos=None,
    commit=False,
    scheme=DEFAULT_RSA_SIGNATURE_SCHEME,
    taf_repo=None,
):
    """
    <Purpose>
        Register all files found in the target directory as targets - updates the targets
        metadata file, snapshot and timestamp. Sign targets
        with yubikey if keystore is not provided
    <Arguments>
        repo_path:
        Authentication repository's path
        keystore:
        Location of the keystore files
        roles_key_infos:
        A dictionary whose keys are role names, while values contain information about the keys.
        commit_msg:
        Commit message. If specified, the changes made to the authentication are committed.
        scheme:
        A signature scheme used for signing.
        taf_repo:
        If taf repository is already initialized, it can be passed and used.
    """
    print("Signing target files")
    roles_key_infos, keystore = _initialize_roles_and_keystore(
        roles_key_infos, keystore, enter_info=False
    )
    roles_infos = roles_key_infos.get("roles")
    if taf_repo is None:
        repo_path = Path(repo_path).resolve()
        taf_repo = Repository(str(repo_path))

    # find files that should be added/modified/removed
    added_targets_data, removed_targets_data = taf_repo.get_all_target_files_state()

    update_target_metadata(
        taf_repo,
        added_targets_data,
        removed_targets_data,
        keystore,
        roles_infos,
        scheme,
    )

    if commit:
        auth_git_repo = GitRepository(path=taf_repo.path)
        commit_message = input("\nEnter commit message and press ENTER\n\n")
        auth_git_repo.commit(commit_message)


def signature_provider(key_id, cert_cn, key, data):  # pylint: disable=W0613
    def _check_key_id(expected_key_id):
        try:
            inserted_key = yk.get_piv_public_key_tuf()
            return expected_key_id == inserted_key["keyid"]
        except Exception:
            return False

    while not _check_key_id(key_id):
        pass

    data = securesystemslib.formats.encode_canonical(data).encode("utf-8")
    key_pin = getpass(f"Please insert {cert_cn} YubiKey, input PIN and press ENTER.\n")
    signature = yk.sign_piv_rsa_pkcs1v15(data, key_pin)

    return {"keyid": key_id, "sig": hexlify(signature).decode()}


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


def update_and_sign_targets(
    repo_path: str,
    library_dir: str,
    target_types: list,
    keystore: str,
    roles_key_infos: str,
    scheme: str,
):
    """
    <Purpose>
        Save the top commit of specified target repositories to the corresponding target files and sign
    <Arguments>
        repo_path:
        Authentication repository's location
        library_dir:
        Directory where target repositories and, optionally, authentication repository are locate
        targets:
        Types of target repositories whose corresponding target files should be updated and signed
        keystore:
        Location of the keystore files
        roles_key_infos:
        A dictionary whose keys are role names, while values contain information about the keys
        no_commit:
        Indicates that the changes should bot get committed automatically
        scheme:
        A signature scheme used for signing

    """
    auth_path = Path(repo_path).resolve()
    auth_repo = AuthenticationRepository(path=auth_path)
    if library_dir is None:
        library_dir = auth_path.parent.parent
    repositoriesdb.load_repositories(auth_repo)
    nonexistent_target_types = []
    target_names = []
    for target_type in target_types:
        try:
            target_name = repositoriesdb.get_repositories_paths_by_custom_data(
                auth_repo, type=target_type
            )[0]
            target_names.append(target_name)
        except Exception:
            nonexistent_target_types.append(target_type)
            continue
    if len(nonexistent_target_types):
        print(
            f"Target types {'.'.join(nonexistent_target_types)} not in repositories.json. Targets not updated"
        )
        return

    # only update target files if all specified types are valid
    for target_name in target_names:
        _save_top_commit_of_repo_to_target(library_dir, target_name, auth_path, True)
        print(f"Updated {target_name} target file")
    register_target_files(auth_path, keystore, roles_key_infos, True, scheme)


def _update_role(taf_repo, role, keystore, roles_infos, scheme):
    keystore_keys, yubikeys = load_signing_keys(
        taf_repo, role, keystore, roles_infos, scheme=scheme
    )
    if len(keystore_keys):
        taf_repo.update_role_keystores(role, keystore_keys, write=False)
    if len(yubikeys):
        taf_repo.update_role_yubikeys(role, yubikeys, write=False)
