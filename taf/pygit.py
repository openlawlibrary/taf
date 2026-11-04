from typing import Dict
import pygit2
from collections import defaultdict
from taf.exceptions import FileTooLargeError, GitError
import os.path

from taf.models.types import Commitish


class PyGitRepository:
    def __init__(
        self,
        encapsulating_repo,
        *args,
        **kwargs,
    ):
        self.encapsulating_repo = encapsulating_repo
        self.path = encapsulating_repo.path
        self.repo = pygit2.Repository(str(self.path))

    _files_cache: Dict = defaultdict(dict)

    def _get_child(self, parent, path_part):
        """
        Return the child object of a parent object.
        Used for walking a git tree.
        """
        try:
            out = parent[path_part]
        except KeyError:
            return None
        else:
            return self.repo[out.id]

    def _get_object_at_path(self, obj, path):
        """
        for the given commit object,
        get the object at the given path
        """
        working = obj.tree
        if path.endswith("/"):
            path = path[:-1]
        path = path.split("/")
        for part in path:
            working = self._get_child(working, part)
            if working is None:
                return None
        return working

    def _get_blob_at_path(self, obj, path):
        """
        for the given commit object,
        get the blob at the given path
        """
        working = self._get_object_at_path(obj, path)
        if working and isinstance(working, pygit2.Blob):
            return working
        return None

    def cleanup(self):
        """
        Must call this function in order to release pygit2 file handles.
        """
        self.repo.free()

    def get_file(self, commit: Commitish, path, raw=False, max_length=None):
        """
        for the given commit string,
        return the string contents of the blob at the
        given path, if it exists, otherwise raise GitError.
        If max_length is given, raise FileTooLargeError for a larger blob
        without reading its content.
        """
        obj = self.repo.get(commit.hash)
        blob = self._get_blob_at_path(obj, path)
        if blob is None:
            raise GitError(
                self.encapsulating_repo,
                message=f"fatal: Path '{path}' does not exist in '{commit}'",
            )
        else:
            git_id = str(blob.id)
            type = "raw" if raw else "decoded"
            cached = self._files_cache.get(git_id, {})
            if max_length is not None:
                size = len(cached["raw"]) if "raw" in cached else self._blob_size(blob)
                if size > max_length:
                    raise FileTooLargeError(path, size, max_length)
            if type not in cached:
                content = blob.read_raw() if raw else blob.read_raw().decode()
                self._files_cache[git_id] |= {type: content}
            return git_id, self._files_cache[git_id][type]

    def _blob_size(self, blob) -> int:
        """
        Read the blob's size from its object header. Reading the content first could
        use far more memory, since a small compressed object can unpack to a large file.
        """
        for backend in self.repo.odb.backends:
            try:
                _, size = backend.read_header(blob.id)
                return size
            except (KeyError, pygit2.GitError):
                continue
        return blob.size

    def _list_files_at_revision(self, tree, path="", results=None):
        """
        recurse through tree and return paths relative to that tree for
        all blobs in that tree.
        """
        if results is None:
            results = []

        for entry in tree:
            new_path = os.path.join(path, entry.name)
            if entry.type_str == "blob":
                results.append(new_path)
            elif entry.type_str == "tree":
                obj = self._get_child(tree, entry.name)
                self._list_files_at_revision(obj, new_path, results)
            else:
                raise NotImplementedError(
                    f"object at '{new_path}' of type '{entry.name}' not supported"
                )
        return results

    def list_files_at_revision(self, commit: Commitish, path: str):
        """
        for the given commit string,
        return a list of all file paths that are
        descendents of the path string.
        """
        obj = self.repo.get(commit.hash)
        root = self._get_object_at_path(obj, path)
        if root is None:
            raise GitError(
                self.encapsulating_repo,
                message=f"fatal: Path '{path}' does not exist in '{commit}'",
            )
        return self._list_files_at_revision(root)
