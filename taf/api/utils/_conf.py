import json

from taf.auth_repo import AuthenticationRepository
from taf.constants import DEFAULT_RSA_SIGNATURE_SCHEME
from taf.config import load_config
from taf.tuf.keys import get_sslib_key_from_value, _get_legacy_keyid
from taf.log import taf_logger
from pathlib import Path
from typing import Dict, Optional, Union


def find_taf_directory(path: Union[Path, str]) -> Optional[Path]:
    """Look for the .taf directory within the archive root.

    Args:
        path (Path): The current path to do the lookup.

    Returns:
        Optional[Path]: The path to the .taf directory if found, otherwise None.
    """
    # Check the parent directory of the authentication repository
    current_dir = Path(path).absolute()
    while current_dir != current_dir.root:
        taf_directory = current_dir / ".taf"
        if taf_directory.exists() and taf_directory.is_dir():
            return taf_directory
        current_dir = current_dir.parent

    # If not found, check the archive root
    archive_root = Path(path).parent.parent
    current_dir = archive_root
    while current_dir != current_dir.root:
        taf_directory = current_dir / ".taf"
        if taf_directory.exists() and taf_directory.is_dir():
            return taf_directory
        current_dir = current_dir.parent

    taf_logger.debug(f"No .taf directory found starting from {Path(path)}")
    return None


def find_keystore(path: Union[str, Path]) -> Optional[Path]:
    """Find keystore starting from the given path and traversing parent directories if needed."""
    taf_directory = find_taf_directory(Path(path))
    if taf_directory:
        keystore_path = taf_directory / "keystore"
        if keystore_path.exists() and keystore_path.is_dir():
            taf_logger.debug(f"Found keystore at {keystore_path}")
            return keystore_path
    taf_logger.debug(f"No keystore found starting from {path}")
    return None


def _build_keys_name_mapping(raw_mapping: Dict) -> Dict[str, str]:
    """
    Internal helper to turn a raw key_name -> key_data mapping into the
    legacy key_id -> key_name mapping used elsewhere.
    """
    keys_name_mappings: Dict[str, str] = {}

    for key_name, key_data in raw_mapping.items():
        scheme = key_data.get("scheme", DEFAULT_RSA_SIGNATURE_SCHEME)

        if "public" in key_data:
            pub_key = key_data["public"]
            try:
                ssl_pub_key = get_sslib_key_from_value(pub_key, scheme=scheme)
                key_id = _get_legacy_keyid(ssl_pub_key)
                keys_name_mappings[key_id] = key_name
            except ValueError:
                taf_logger.log("NOTICE", f"Invalid public key {key_name}")

        elif "keyid" in key_data:
            key_id = key_data["keyid"]
            keys_name_mappings[key_id] = key_name

    return keys_name_mappings


def read_keys_name_mapping(keys_description: Optional[Union[str, Path]]) -> Dict:
    keys_name_mappings: Dict = {}
    if keys_description is None:
        return keys_name_mappings

    keys_description_path = Path(keys_description)
    if not keys_description_path.is_file():
        return keys_name_mappings

    try:
        keys_description_data = json.loads(keys_description_path.read_text())
    except json.decoder.JSONDecodeError:
        return keys_name_mappings

    key_names_mapping = keys_description_data.get("yubikeys")

    return _build_keys_name_mapping(key_names_mapping) if key_names_mapping else {}


def read_keys_name_mapping_from_auth(auth_repo: AuthenticationRepository) -> Dict:
    """
    Read the keys name mapping from the authentication repository.
    """
    taf_dir = find_taf_directory(auth_repo.path)
    if taf_dir is None:
        return {}

    try:
        cfg = load_config(taf_dir / "config.toml")
        if cfg.root is None:
            raise FileNotFoundError("No root authentication repository found.")
    except FileNotFoundError:
        return {}

    root_auth_repo_name = cfg.root.name
    archive_dir = taf_dir.parent
    root_auth_repo = AuthenticationRepository(path=(archive_dir / root_auth_repo_name))
    if not root_auth_repo.is_git_repository:
        taf_logger.debug(
            f"{root_auth_repo_name} is not a valid authentication repository."
        )
        return {}

    raw_mapping = root_auth_repo.get_keys_mapping() or {}
    return _build_keys_name_mapping(raw_mapping)
