from taf.log import taf_logger
from pathlib import Path
from typing import Optional

def find_taf_directory(auth_repo_path: Path) -> Optional[Path]:
    """Look for the .taf directory within the archive root.

    Args:
        auth_repo_path (Path): The path to the authentication repository.

    Returns:
        Optional[Path]: The path to the .taf directory if found, otherwise None.
    """
    # Determine the archive root
    archive_root = auth_repo_path.parent.parent

    current_dir = archive_root
    while current_dir != current_dir.root:
        taf_directory = current_dir / ".taf"
        if taf_directory.exists() and taf_directory.is_dir():
            return taf_directory
        current_dir = current_dir.parent

    taf_logger.info(f"No .taf directory found starting from {archive_root}")
    return None

def find_keystore(path: Path) -> Optional[Path]:
    """
    Find keystore starting from the given path and traversing parent directories if needed.
    """
    for parent in [path] + list(path.parents):
        keystore_path = parent / "keystore"
        if keystore_path.exists() and keystore_path.is_dir():
            taf_logger.info(f"Found default keystore at {keystore_path}")
            return keystore_path
    taf_logger.info(f"No default keystore found starting from {path}")
    return None