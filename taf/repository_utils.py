#File for Utility functions that cause circular import errors in utils.py
from pathlib import Path
from taf.exceptions import InvalidRepositoryError
from taf.auth_repo import AuthenticationRepository
from taf.utils import taf_logger
from tuf.exceptions import RepositoryError

def find_valid_repository(path: Path) -> Path:
    """
    Find a valid authentication repository starting from the given path and traversing subdirectories and parent directories if needed.
    """

    def try_load_repository(repo_path: Path) -> bool:
        try:
            auth_repo = AuthenticationRepository(path=repo_path)
            if auth_repo.get_metadata("root") is not None:
                taf_logger.info(f"Loaded valid authentication repository from {repo_path}")
                return True
            return False
        except RepositoryError:
            return False

    # First, try to load the repository from the given path
    if try_load_repository(path):
        return path

    # Search subdirectories
    taf_logger.debug(
        f"Current directory {path} is not a valid authentication repository. Searching subdirectories..."
    )

    subdirs = [subdir for subdir in path.iterdir() if subdir.is_dir()]

    for subdir_path in subdirs:
        if try_load_repository(subdir_path):
            return subdir_path

    # Search parent directories
    taf_logger.debug(
        f"Current directory {path} is not a valid authentication repository. Searching parent directories..."
    )

    current_path = path
    while current_path != current_path.parent:  
        current_path = current_path.parent
        if try_load_repository(current_path):
            return current_path

    raise InvalidRepositoryError(
        f"Could not find a valid authentication repository in {path} or any of its subdirectories or parent directories."
    )