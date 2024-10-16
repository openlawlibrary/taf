"""
This module contains utility functions that cause circular import errors in utils.py.
"""

from pathlib import Path
from taf.exceptions import GitError, InvalidRepositoryError
from taf.auth_repo import AuthenticationRepository
from taf.git import GitRepository
from taf.utils import taf_logger


def find_valid_repository(path: Path) -> Path:
    """
    Find a valid authentication repository starting from the given path and traversing subdirectories and parent directories if needed.
    """

    def try_load_repository(repo_path: Path) -> bool:
        try:
            auth_repo = AuthenticationRepository(path=repo_path)
            if auth_repo.get_metadata("root") is not None:
                taf_logger.info(
                    f"Loaded valid authentication repository from {repo_path}"
                )
                return True
            return False
        except GitError:
            return False

    path = Path(path).resolve()
    if not path.is_dir():
        raise InvalidRepositoryError(f"Directory {path} does not exist")
    # First, try to load the repository from the given path
    if try_load_repository(path):
        # find the git repository's root
        current_path = path
        while not GitRepository(path=current_path).is_git_repository_root:
            current_path = current_path.parent
        return current_path

    # Search subdirectories
    taf_logger.debug(
        f"Current directory {path} is not a valid authentication repository. Searching subdirectories..."
    )
    for subdir in path.iterdir():
        if subdir.is_dir() and try_load_repository(subdir):
            return subdir

    raise InvalidRepositoryError(
        f"Could not find a valid authentication repository in {path} or any of its subdirectories or parent directories."
    )
