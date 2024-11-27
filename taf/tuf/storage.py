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
    for path, repo in git_repos_cache.items():
        if is_subpath(inner_path, path):
            return repo
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

    commit: Optional[str] = None

    def __new__(cls, *args, **kwargs):
        return super(FilesystemBackend, cls).__new__(
            cls, *args, **kwargs
        )  # Bypass singleton

    @contextmanager
    def get(self, filepath: str):
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
        repo_path = pygit2.discover_repository(filepath)
        if repo_path:
            repo = find_git_repository(filepath)
            if repo.is_bare_repository:
                raise TAFError(
                    f"Cannot write to {filepath}. Repository is a bare repository"
                )
        super().put(fileobj, filepath, restrict)
