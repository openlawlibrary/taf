from contextlib import contextmanager
import io
from pathlib import Path
from typing import IO, Dict, Optional
import pygit2
from taf.constants import METADATA_DIRECTORY_NAME
from taf.exceptions import GitError, TAFError
from taf.git import GitRepository

from securesystemslib.storage import FilesystemBackend

from securesystemslib.exceptions import StorageError
from taf.models.types import Commitish

git_repos_cache: Dict[str, GitRepository] = {}


def is_subpath(path, potential_subpath):
    path = Path(path).resolve()
    potential_subpath = Path(potential_subpath).resolve()

    try:
        potential_subpath.relative_to(path)
        return True
    except ValueError:
        return False


def find_git_repository(inner_path):
    """
    Instantiates a git repository based on a path
    that is expected to be inside that repository.
    Enables smoother integration with TUF's default
    FilesystemBackend implementation
    """
    for path in list(git_repos_cache.keys()):
        if is_subpath(path, inner_path):
            return git_repos_cache[path]
    repo_path = pygit2.discover_repository(inner_path)
    repo = None
    if not repo_path:
        # could be a bare repository
        repo_path = str(inner_path).split(METADATA_DIRECTORY_NAME)[0]
        if repo_path:
            try:
                pygit2.Repository(repo_path)
            except Exception:
                return None
            else:
                repo = GitRepository(path=repo_path)
    else:
        repo_path = Path(repo_path).parent
        repo = GitRepository(path=repo_path)

    if repo:
        git_repos_cache[repo.path] = repo
    return repo


class GitStorageBackend(FilesystemBackend):
    """
    Storage backend implemnantation that loads data
    from a specific commit, if it is specified,
    or from the filesystem, if the commit is None
    Extends TUF's FilesystemBackend.
    """

    commit: Optional[Commitish] = None

    def __new__(cls, *args, **kwargs):
        # Bypass singleton
        # This is necessary in order to use this within the context of
        # parallel update of multiple repositories
        return super(FilesystemBackend, cls).__new__(cls, *args, **kwargs)

    @contextmanager
    def get(self, filepath: str):
        # If the commit is specified, read from Git.
        # If it is not specified, read from the filesystem.
        if self.commit is None:
            with super().get(filepath=filepath) as value_from_base:
                yield value_from_base
        else:
            try:
                repo = find_git_repository(filepath)
                file_path = Path(filepath)
                relative_path = file_path.relative_to(repo.path)
                data = repo.get_file(self.commit, relative_path).encode()
                yield io.BytesIO(data)
            except GitError as e:
                raise StorageError(e)
            except TAFError as e:
                raise StorageError(e)

    def getsize(self, filepath: str) -> int:
        # Get size of a file after reading it from Git or the filesystem.
        # If the commit is specified, read from Git.
        # If it is not specified, read from the filesystem.
        if self.commit is None:
            return super().getsize(filepath=filepath)
        try:
            repo = find_git_repository(filepath)
            file_path = Path(filepath)
            relative_path = file_path.relative_to(repo.path)
            data = repo.get_file(self.commit, relative_path).encode()
            return len(data)
        except GitError as e:
            raise StorageError(e)
        except TAFError as e:
            raise StorageError(e)

    def put(self, fileobj: IO, filepath: str, restrict: Optional[bool] = False) -> None:
        # Write the file to the filesystem.
        # Raise an error if the repository is a bare repository.
        repo_path = pygit2.discover_repository(filepath)
        if repo_path:
            repo = find_git_repository(filepath)
            if repo.is_bare_repository:
                raise TAFError(
                    f"Cannot write to {filepath}. Repository is a bare repository"
                )
        super().put(fileobj, filepath, restrict)
