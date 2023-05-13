import json
from binascii import hexlify
from collections import defaultdict
from functools import partial
from getpass import getpass
from pathlib import Path

import securesystemslib
import securesystemslib.exceptions
from taf.api.repository import register_target_files
from taf.api.roles import _create_delegations, _initialize_roles_and_keystore, _role_obj
from taf.api.metadata import update_snapshot_and_timestamp, update_target_metadata
from taf.api.targets import (
    _save_top_commit_of_repo_to_target,
)
from taf import YubikeyMissingLibrary

try:
    import taf.yubikey as yk
except ImportError:
    yk = YubikeyMissingLibrary()


from tuf.repository_tool import (
    TARGETS_DIRECTORY_NAME,
    create_new_repository,
)


from taf.auth_repo import AuthenticationRepository
from taf.constants import (
    DEFAULT_RSA_SIGNATURE_SCHEME,
)
from taf.exceptions import KeystoreError, TargetsMetadataUpdateError

import taf.repositoriesdb as repositoriesdb


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
